import copy
import json
import os.path as op
from inspect import getmro
from typing import Type, Optional

from urllib.parse import urlencode
from .exceptions import ObjectDoesNotExist
from .mixins import ReplicatedMixin, ScalableMixin
from .query import Query
from .utils import obj_merge
from .http import HTTPClient


class ObjectManager:
    def __call__(self, api: HTTPClient, namespace: str = None):
        if namespace is None and NamespacedAPIObject in getmro(self.api_obj_class):
            namespace = api.config.namespace
        return Query(api, self.api_obj_class, namespace=namespace)

    def __get__(self, obj, api_obj_class: Type):
        assert obj is None, "cannot invoke objects on resource object."
        self.api_obj_class = api_obj_class
        return self


class APIObject:
    """
    Baseclass for all Kubernetes API objects
    """

    objects = ObjectManager()
    base = None

    def __init__(self, api: HTTPClient, obj: dict):
        self.api = api
        self.set_obj(obj)

    def set_obj(self, obj: dict):
        self.obj = obj
        self._original_obj = copy.deepcopy(obj)

    def __repr__(self):
        return f"<{self.kind} {self.name}>"

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """
        Name of the Kubernetes resource (metadata.name)

        Name must be unique within a namespace. Is required when creating resources, although some resources may allow a client to request the generation
        of an appropriate name automatically. Name is primarily intended for creation idempotence and configuration definition.
        Cannot be updated. More info: http://kubernetes.io/docs/user-guide/identifiers#names
        """
        return self.obj["metadata"]["name"]

    @property
    def namespace(self) -> Optional[str]:
        return None

    @property
    def metadata(self):
        return self.obj["metadata"]

    @property
    def labels(self) -> dict:
        """
        Labels of the Kubernetes resource (metadata.labels)

        Map of string keys and values that can be used to organize and categorize (scope and select) objects.
        May match selectors of replication controllers and services. More info: http://kubernetes.io/docs/user-guide/labels
        """
        return self.obj["metadata"].setdefault("labels", {})

    @property
    def annotations(self) -> dict:
        """
        Annotations of the Kubernetes resource (metadata.annotations)

        Annotations is an unstructured key value map stored with a resource that may be set by external tools to store and retrieve arbitrary metadata.
        They are not queryable and should be preserved when modifying objects. More info: http://kubernetes.io/docs/user-guide/annotations
        """
        return self.obj["metadata"].setdefault("annotations", {})

    def api_kwargs(self, **kwargs):
        kw = {}
        # Construct url for api request
        obj_list = kwargs.pop("obj_list", False)
        if obj_list:
            kw["url"] = self.endpoint
        else:
            operation = kwargs.pop("operation", "")
            kw["url"] = op.normpath(op.join(self.endpoint, self.name, operation))
        params = kwargs.pop("params", None)
        if params is not None:
            query_string = urlencode(params)
            kw["url"] = "{}{}".format(
                kw["url"], f"?{query_string}" if query_string else ""
            )
        if self.base:
            kw["base"] = self.base
        kw["version"] = self.version
        if self.namespace is not None:
            kw["namespace"] = self.namespace
        kw.update(kwargs)
        return kw

    def exists(self, ensure=False):
        r = self.api.get(**self.api_kwargs())
        if r.status_code not in {200, 404}:
            self.api.raise_for_status(r)
        if not r.ok:
            if ensure:
                raise ObjectDoesNotExist(f"{self.name} does not exist.")
            else:
                return False
        return True

    def create(self):
        r = self.api.post(**self.api_kwargs(data=json.dumps(self.obj), obj_list=True))
        self.api.raise_for_status(r)
        self.set_obj(r.json())

    def reload(self):
        r = self.api.get(**self.api_kwargs())
        self.api.raise_for_status(r)
        self.set_obj(r.json())

    def watch(self):
        return (
            self.__class__.objects(self.api, namespace=self.namespace)
            .filter(field_selector={"metadata.name": self.name})
            .watch()
        )

    def patch(self, strategic_merge_patch):
        """
        Patch the Kubernetes resource by calling the API with a "strategic merge" patch.
        """
        r = self.api.patch(
            **self.api_kwargs(
                headers={"Content-Type": "application/merge-patch+json"},
                data=json.dumps(strategic_merge_patch),
            )
        )
        self.api.raise_for_status(r)
        self.set_obj(r.json())

    def update(self, is_strategic=True):
        """
        Update the Kubernetes resource by calling the API (patch)
        """
        self.obj = obj_merge(self.obj, self._original_obj, is_strategic)
        self.patch(self.obj)

    def delete(self, propagation_policy: str = None):
        """
        Delete the Kubernetes resource by calling the API.

        The parameter propagation_policy defines whether to cascade the delete. It can be "Foreground", "Background" or "Orphan".
        See https://kubernetes.io/docs/concepts/workloads/controllers/garbage-collection/#setting-the-cascading-deletion-policy
        """
        if propagation_policy:
            options = {"propagationPolicy": propagation_policy}
        else:
            options = {}
        r = self.api.delete(**self.api_kwargs(data=json.dumps(options)))
        if r.status_code != 404:
            self.api.raise_for_status(r)


class NamespacedAPIObject(APIObject):
    @property
    def namespace(self) -> str:
        """
        Namespace scope of the Kubernetes resource (metadata.namespace)

        Namespace defines the space within each name must be unique.
        Cannot be updated. More info: http://kubernetes.io/docs/user-guide/namespaces
        """
        if self.obj["metadata"].get("namespace"):
            return self.obj["metadata"]["namespace"]
        else:
            return self.api.config.namespace


def object_factory(api, api_version, kind) -> Type[APIObject]:
    """
    Dynamically builds a Python class for the given Kubernetes object in an API.

    For example:

        api = pykube.HTTPClient(...)
        NetworkPolicy = pykube.object_factory(api, "networking.k8s.io/v1", "NetworkPolicy")

    This enables construction of any Kubernetes object kind without explicit support
    from pykube.

    Currently, the HTTPClient passed to this function will not be bound to the returned type.
    It is planned to fix this, but in the mean time pass it as you would normally.
    """
    resource_list = api.resource_list(api_version)
    try:
        resource = next(
            resource
            for resource in resource_list["resources"]
            if resource["kind"] == kind
        )
    except StopIteration:
        raise ValueError("unknown resource kind {!r}".format(kind)) from None
    base = NamespacedAPIObject if resource["namespaced"] else APIObject
    return type(
        kind,
        (base,),
        {"version": api_version, "endpoint": resource["name"], "kind": kind},
    )


class ConfigMap(NamespacedAPIObject):

    version = "v1"
    endpoint = "configmaps"
    kind = "ConfigMap"


class CronJob(NamespacedAPIObject):

    version = "batch/v1beta1"
    endpoint = "cronjobs"
    kind = "CronJob"


class DaemonSet(NamespacedAPIObject):

    version = "apps/v1"
    endpoint = "daemonsets"
    kind = "DaemonSet"


class Deployment(NamespacedAPIObject, ReplicatedMixin, ScalableMixin):

    version = "apps/v1"
    endpoint = "deployments"
    kind = "Deployment"

    @property
    def ready(self):
        return (
            self.obj["status"]["observedGeneration"]
            >= self.obj["metadata"]["generation"]
            and self.obj["status"]["updatedReplicas"] == self.replicas
        )

    def rollout_undo(self, target_revision=None):
        """Produces same action as kubectl rollout undo deployment command.
        Input variable is revision to rollback to (in kubectl, --to-revision)
        """
        if target_revision is None:
            revision = {}
        else:
            revision = {"revision": target_revision}

        params = {
            "kind": "DeploymentRollback",
            "apiVersion": self.version,
            "name": self.name,
            "rollbackTo": revision,
        }

        kwargs = {
            "version": self.version,
            "namespace": self.namespace,
            "operation": "rollback",
        }
        r = self.api.post(**self.api_kwargs(data=json.dumps(params), **kwargs))
        r.raise_for_status()
        return r.text


class Endpoint(NamespacedAPIObject):

    version = "v1"
    endpoint = "endpoints"
    kind = "Endpoint"


class Event(NamespacedAPIObject):

    version = "v1"
    endpoint = "events"
    kind = "Event"


class LimitRange(NamespacedAPIObject):

    version = "v1"
    endpoint = "limitranges"
    kind = "LimitRange"


class ResourceQuota(NamespacedAPIObject):

    version = "v1"
    endpoint = "resourcequotas"
    kind = "ResourceQuota"


class ServiceAccount(NamespacedAPIObject):

    version = "v1"
    endpoint = "serviceaccounts"
    kind = "ServiceAccount"


class Ingress(NamespacedAPIObject):

    version = "extensions/v1beta1"
    endpoint = "ingresses"
    kind = "Ingress"


class ThirdPartyResource(APIObject):

    version = "extensions/v1beta1"
    endpoint = "thirdpartyresources"
    kind = "ThirdPartyResource"


class Job(NamespacedAPIObject, ScalableMixin):

    version = "batch/v1"
    endpoint = "jobs"
    kind = "Job"
    scalable_attr = "parallelism"

    @property
    def parallelism(self):
        return self.obj["spec"]["parallelism"]

    @parallelism.setter
    def parallelism(self, value):
        self.obj["spec"]["parallelism"] = value


class Namespace(APIObject):

    version = "v1"
    endpoint = "namespaces"
    kind = "Namespace"


class Node(APIObject):

    version = "v1"
    endpoint = "nodes"
    kind = "Node"

    @property
    def unschedulable(self):
        if "unschedulable" in self.obj["spec"]:
            return self.obj["spec"]["unschedulable"]
        return False

    @unschedulable.setter
    def unschedulable(self, value):
        self.obj["spec"]["unschedulable"] = value
        self.update()

    def cordon(self):
        self.unschedulable = True

    def uncordon(self):
        self.unschedulable = False


class Pod(NamespacedAPIObject):

    version = "v1"
    endpoint = "pods"
    kind = "Pod"

    @property
    def ready(self):
        cs = self.obj["status"].get("conditions", [])
        condition = next((c for c in cs if c["type"] == "Ready"), None)
        return condition is not None and condition["status"] == "True"

    def logs(
        self,
        container=None,
        pretty=None,
        previous=False,
        since_seconds=None,
        since_time=None,
        timestamps=False,
        tail_lines=None,
        limit_bytes=None,
    ):
        """
        Produces the same result as calling kubectl logs pod/<pod-name>.
        Check parameters meaning at
        http://kubernetes.io/docs/api-reference/v1/operations/,
        part 'read log of the specified Pod'. The result is plain text.
        """
        log_call = "log"
        params = {}
        if container is not None:
            params["container"] = container
        if pretty is not None:
            params["pretty"] = pretty
        if previous:
            params["previous"] = "true"
        if since_seconds is not None and since_time is None:
            params["sinceSeconds"] = int(since_seconds)
        elif since_time is not None and since_seconds is None:
            params["sinceTime"] = since_time
        if timestamps:
            params["timestamps"] = "true"
        if tail_lines is not None:
            params["tailLines"] = int(tail_lines)
        if limit_bytes is not None:
            params["limitBytes"] = int(limit_bytes)

        query_string = urlencode(params)
        log_call += f"?{query_string}" if query_string else ""
        kwargs = {
            "version": self.version,
            "namespace": self.namespace,
            "operation": log_call,
        }
        r = self.api.get(**self.api_kwargs(**kwargs))
        r.raise_for_status()
        return r.text


class ReplicationController(NamespacedAPIObject, ReplicatedMixin, ScalableMixin):

    version = "v1"
    endpoint = "replicationcontrollers"
    kind = "ReplicationController"

    @property
    def ready(self):
        return (
            self.obj["status"]["observedGeneration"]
            >= self.obj["metadata"]["generation"]
            and self.obj["status"]["readyReplicas"] == self.replicas
        )


class ReplicaSet(NamespacedAPIObject, ReplicatedMixin, ScalableMixin):

    version = "apps/v1"
    endpoint = "replicasets"
    kind = "ReplicaSet"


class Secret(NamespacedAPIObject):

    version = "v1"
    endpoint = "secrets"
    kind = "Secret"


class Service(NamespacedAPIObject):

    version = "v1"
    endpoint = "services"
    kind = "Service"


class PersistentVolume(APIObject):

    version = "v1"
    endpoint = "persistentvolumes"
    kind = "PersistentVolume"


class PersistentVolumeClaim(NamespacedAPIObject):

    version = "v1"
    endpoint = "persistentvolumeclaims"
    kind = "PersistentVolumeClaim"


class HorizontalPodAutoscaler(NamespacedAPIObject):

    version = "autoscaling/v1"
    endpoint = "horizontalpodautoscalers"
    kind = "HorizontalPodAutoscaler"


class StatefulSet(NamespacedAPIObject, ReplicatedMixin, ScalableMixin):

    version = "apps/v1"
    endpoint = "statefulsets"
    kind = "StatefulSet"


class Role(NamespacedAPIObject):

    version = "rbac.authorization.k8s.io/v1"
    endpoint = "roles"
    kind = "Role"


class RoleBinding(NamespacedAPIObject):

    version = "rbac.authorization.k8s.io/v1"
    endpoint = "rolebindings"
    kind = "RoleBinding"


class ClusterRole(APIObject):

    version = "rbac.authorization.k8s.io/v1"
    endpoint = "clusterroles"
    kind = "ClusterRole"


class ClusterRoleBinding(APIObject):

    version = "rbac.authorization.k8s.io/v1"
    endpoint = "clusterrolebindings"
    kind = "ClusterRoleBinding"


class PodSecurityPolicy(APIObject):

    version = "extensions/v1beta1"
    endpoint = "podsecuritypolicies"
    kind = "PodSecurityPolicy"


class PodDisruptionBudget(NamespacedAPIObject):

    version = "policy/v1beta1"
    endpoint = "poddisruptionbudgets"
    kind = "PodDisruptionBudget"


class CustomResourceDefinition(APIObject):

    version = "apiextensions.k8s.io/v1beta1"
    endpoint = "customresourcedefinitions"
    kind = "CustomResourceDefinition"
