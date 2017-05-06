# encoding: utf-8

from . import tool_utils

from acmd.repo import import_tools

get_command = tool_utils.get_command
get_argument = tool_utils.get_argument
filter_system = tool_utils.filter_system


def init_default_tools(config=None):
    import_tools(__file__, 'acmd.tools', prefix=None, config=config)
