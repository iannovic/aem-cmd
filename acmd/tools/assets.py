# coding: utf-8
import optparse
import re
import sys

import acmd.jcr.path
from acmd import OK, SERVER_ERROR, USER_ERROR, tool, error, log
from acmd.assets import AssetsApi, AssetsImportFunnel
from acmd.tools.tool_utils import get_argument, get_command
from acmd.workflows import WorkflowsApi

parser = optparse.OptionParser("acmd assets <import|touch> [options] <file>")
parser.add_option("-r", "--raw",
                  action="store_const", const=True, dest="raw",
                  help="output raw response data")
parser.add_option("-D", "--dry-run",
                  action="store_const", const=True, dest="dry_run",
                  help="Do not change repository")
parser.add_option("-d", "--destination", dest="destination_root",
                  help="The root directory to import to")
parser.add_option("-m", "--model", dest="model", default="dam/update_asset",
                  help="Update assets model to use, defaults to dam/update_asset")


@tool('assets')
class AssetsTool(object):
    """ Manage AEM DAM assets """

    def __init__(self):
        self.created_paths = set([])
        self.current_file = 1
        self.api = None

    def execute(self, server, argv):
        self.api = AssetsApi(server)

        options, args = parser.parse_args(argv)

        action = get_command(args)
        actionarg = get_argument(args)

        if action == 'import':
            funnel = AssetsImportFunnel(server, dry_run=options.dry_run, destination_root=options.destination_root)
            return funnel.import_path(actionarg)
        elif action == 'touch':
            api = WorkflowsApi(server)
            if len(args) >= 3:
                self.touch_asset(api, actionarg, options.model)
            else:
                for line in sys.stdin:
                    self.touch_asset(api, line.strip(), options.model)
            return OK
        elif action == 'list' or action == 'ls':
            status, data = self.api.list(actionarg)
            if status != OK:
                return status
            for item in data['entities']:
                print item['properties']['name']
            return OK
        elif action == 'find':
            status, data = self.api.find(actionarg)
            if status != OK:
                return status
            for item in data:
                props = item['properties']
                path = acmd.jcr.path.join(props['path'], props['name'])
                sys.stdout.write("{}\n".format(path))
        elif action == 'tag':
            tag_str = get_argument(args)
            status, tags = parse_tags(tag_str)
            if status != OK:
                return status
            if len(args) <= 3:
                log("Reading files from input")
                for path in sys.stdin:
                    path = path.strip()
                    self.tag_asset(path, tags)
            else:
                path = get_argument(args, i=3)
                log("Tagging {}".format(path))
                self.tag_asset(path, tags)
            return OK
        else:
            error("Unknown action {}".format(action))
            return USER_ERROR

    @staticmethod
    def touch_asset(api, path, model):
        path = "/content/dam" + path + "/jcr:content/renditions/original"
        log("Triggering workflow {} on {}".format(model, path))

        api.start_workflow(model, path)
        print path

    def tag_asset(self, assetpath, tags):
        """
        Function is lowlevel and does not look up values from titles.

        assetpath: e.g. /my_robots/bernard.jpg
        propname: e.g. metadata/project_state
        tagname: e.g. westword:project_states/discontinued
        """
        if assetpath.startswith("/content/dam"):
            assetpath = assetpath[len("/content/dam"):]

        status, data = self.api.get(assetpath)
        if status != OK:
            error("Failed to get status for {}: {}".format(assetpath, data))
            return SERVER_ERROR, None
        props = data['properties']

        existing_tags = flatten_properties(props)
        tags = merge_tags(existing_tags, tags)

        status, data = self.api.setprops(assetpath, tags)

        if status != OK:
            error("Failed to update metadata of {}".format(assetpath))
            return status, None
        return OK, data


def merge_tags(existing_tags, new_tags):
    """ Expects two dicts, The first is existing tags {<str> -> <list>}
        The second is new tags {<str> -> <str>}
        Returns a merged dict with all keys and lists merged removing duplicates. {<str> -> <list>}
    """
    ret = existing_tags.copy()
    for key, val in new_tags.items():
        cur = ret.get(key, list())
        if type(cur) != list:
            error("Unexpected type {} for property {}".format(type(cur), key))
            return None
        if type(val) == str:
            cur = add_new(cur, val)
        elif type(val) == list:
            [add_new(cur, v) for v in val]
        ret[key] = cur
    return ret


def add_new(lst, val):
    if val not in lst:
        lst.append(val)
    return lst


def flatten_properties(props):
    """ Fetch data data from api metadata properties """
    ret = dict()
    for key, val in props.items():
        if type(val) == dict:
            sub_props = flatten_properties(val)
            for subkey, subval in sub_props.items():
                ret[key + '/' + subkey] = subval
        else:
            ret[key] = val
    return ret


def parse_tags(tags_expr):
    """ Expects key0=val0,key1=val1 """
    tag_exprs = re.split('(?<!\\\\),', tags_expr)

    ret = dict()
    for tag_expr in tag_exprs:
        status, key, tag = parse_tag(tag_expr)
        if status != OK:
            return status, None
        ret[key] = tag
    return OK, ret


def parse_tag(tag_expr):
    """ Expects key=val """
    parts = re.split("(?<!\\\\)=", tag_expr)
    if len(parts) != 2:
        error("Failed to parse tag parameter string")
        return USER_ERROR, None, None
    return OK, decode(parts[0]), decode(parts[1])


def decode(msg):
    return msg.replace('\=', '=')
