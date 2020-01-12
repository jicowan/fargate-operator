import re

try:
    from jsonpath_ng import parse as jsonpath

    jsonpath_installed = True
except ImportError:
    jsonpath_installed = False

from itertools import zip_longest


empty = object()


def obj_merge(obj, original_obj, is_strategic=True):
    c = {}
    for k, v in obj.items():
        if k not in original_obj:
            c[k] = v
        else:
            c[k] = obj_check(v, original_obj[k], is_strategic)

    if is_strategic is True:
        for k, v in original_obj.items():
            if k not in obj:
                c[k] = v
    return c


def obj_check(obj_value, original_obj_value, is_strategic=True):
    check_result = None
    if not isinstance(obj_value, type(original_obj_value)):
        check_result = obj_value
    else:
        if isinstance(obj_value, dict):
            check_result = obj_merge(obj_value, original_obj_value, is_strategic)

        elif isinstance(obj_value, list):
            if is_strategic:
                res_list = []
                for x, y in zip_longest(obj_value, original_obj_value, fillvalue=empty):
                    if x is empty:
                        res_list.append(y)
                    elif y is empty:
                        res_list.append(x)
                    else:
                        res_list.append(obj_check(x, y, is_strategic))
                check_result = res_list
            else:
                check_result = obj_value
        else:
            check_result = obj_value
    return check_result


def jsonpath_parse(template, obj):
    def repl(m):
        path = m.group(2)
        if not path.startswith("$"):
            path = "$" + path
        return jsonpath(path).find(obj)[0].value

    return re.sub(r"(\{([^\}]*)\})", repl, template)
