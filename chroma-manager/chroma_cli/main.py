#
# ========================================================
# Copyright (c) 2012 Whamcloud, Inc.  All rights reserved.
# ========================================================


from argparse import REMAINDER
import sys
import traceback

from chroma_cli.exceptions import BadRequest, InternalError, NotFound
from chroma_cli.parser import ResettableArgumentParser
from chroma_cli.config import Configuration
from chroma_cli.api import ApiHandle
from chroma_cli.output import StandardFormatter
from chroma_cli.handlers import Dispatcher

# TODO: This kind of thing is probably a good candidate for
# pluginization, if we wind up with a lot of command modules.
from chroma_cli.commands import api_resources


def api_cli():
    config = Configuration()
    parser = ResettableArgumentParser(description="Chroma API CLI")

    # register global arguments for each module
    api_resources.register_global_arguments(parser)

    # freeze global arguments
    parser.clear_resets()

    # first-phase positional arguments
    parser.add_argument("resource", help='command or resource ("resources list") for a list')
    parser.add_argument("verb", nargs="?", help="action to perform on specified resource, if appropriate")
    parser.add_argument("args", nargs=REMAINDER, help="arguments for resource verb")

    ns = parser.parse_args()

    # Allow CLI options to override defaults/.chroma config values
    config.update(dict([[key, val] for key, val in ns.__dict__.items()
                                if val != None
                                and key not in ["resource", "verb", "args"]]))

    command_dispatcher = {}
    # each module can register a set of static command handlers
    command_dispatcher.update(api_resources.commands())

    try:
        # Static handlers
        dispatcher = command_dispatcher[ns.resource]
    except KeyError:
        # Dynamic handlers from API introspection
        dispatcher = api_resources.dispatch

    try:
        dispatcher(config, parser, ns)
    except BadRequest, e:
        print "Validation errors:"
        print e
        sys.exit(1)
    except InternalError, e:
        print "Internal server error:"
        print e
        sys.exit(2)
    except NotFound, e:
        print "Not found:"
        print e
        sys.exit(4)
    except Exception, e:
        # Handlers are plugin-like so do some unexpected exception handling
        exc_info = sys.exc_info()
        trace = '\n'.join(traceback.format_exception(*(exc_info or sys.exc_info())))
        print "Internal client error from handler '%s': %s" % (dispatcher, trace)
        sys.exit(3)


def standard_cli(args=None):
    config = Configuration()
    parser = ResettableArgumentParser(description="Chroma API CLI")
    dispatcher = Dispatcher()

    parser.add_argument("--api-url", help="Entry URL for Chroma API")
    parser.add_argument("--username", help="Chroma username")
    parser.add_argument("--password", help="Chroma password")
    parser.add_argument("--output", "-o", help="Output format",
                        choices=StandardFormatter.formats())
    parser.add_argument("--nowait", help="Don't wait for jobs to complete",
                        action="store_true")
    parser.clear_resets()

    parser.add_argument("primary_action", choices=dispatcher.handled_actions)
    parser.add_argument("options", nargs=REMAINDER)

    ns = parser.parse_args(args)

    # Allow CLI options to override defaults/.chroma config values
    config.update(dict([[key, val] for key, val in ns.__dict__.items()
                                if val != None
                                and key not in ["primary_action", "options"]]))

    authentication = {'username': config.username,
                      'password': config.password}
    api = ApiHandle(api_uri=config.api_url,
                    authentication=authentication)

    formatter = StandardFormatter(format=config.output, nowait=config.nowait, command_monitor=api.command_monitor)

    from chroma_cli.exceptions import ApiException
    try:
        dispatcher(ns.primary_action)(api=api, formatter=formatter)(parser=parser, args=args, namespace=ns)
    except ApiException, e:
        print e
        sys.exit(1)
    except Exception, e:
        exc_info = sys.exc_info()
        trace = '\n'.join(traceback.format_exception(*(exc_info or sys.exc_info())))
        print "Internal client error from handler '%s': %s" % (ns.primary_action, trace)

    sys.exit(0)

if __name__ == '__main__':
    standard_cli()
