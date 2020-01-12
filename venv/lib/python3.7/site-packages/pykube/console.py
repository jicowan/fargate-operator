import argparse
import code

import pykube

# import readline to support line editing within console session.
try:
    import readline  # noqa
except ImportError:
    pass


def main(argv=None):
    """
    Run the interactive Pykube console (usually invoked via python3 -m pykube)
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kubeconfig", help="Path to the kubeconfig file to use", metavar="PATH"
    )
    parser.add_argument(
        "--context", help="The name of the kubeconfig context to used", metavar="NAME"
    )
    parser.add_argument(
        "-c", help="Python program passed in as string", metavar="SCRIPT"
    )
    args = parser.parse_args(argv)

    config = pykube.KubeConfig.from_file(args.kubeconfig)

    if args.context:
        config.set_current_context(args.context)

    api = pykube.HTTPClient(config)

    context = {
        "__name__": "__console__",
        "pykube": pykube,
        "config": config,
        "api": api,
    }
    for k, v in vars(pykube).items():
        if k[0] != "_" and k[0] == k[0].upper():
            context[k] = v

    banner = f"""Pykube v{pykube.__version__}, loaded "{config.filename}" with context "{config.current_context}".

    Example commands:
      [d.name for d in Deployment.objects(api)]              # get names of deployments in default namespace
      list(DaemonSet.objects(api, namespace='kube-system'))  # list daemonsets in "kube-system"
      Pod.objects(api).get_by_name('mypod').labels           # labels of pod "mypod"

    Use Ctrl-D to exit"""

    console = code.InteractiveConsole(locals=context)
    if args.c:
        console.runsource(args.c)
    else:
        console.interact(banner)
