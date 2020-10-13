import time
import argparse
import pprint
import json
import re
import os

## Constants
DEFAULT_DEBUG_LOG_FILE_PATH = "debug.log"
DEFAULT_DEBUG_LOG_OUT_PATH = "debug_parsed.json"

KEY_PROCESS_VERSIONS = "process.versions"
KEY_RAISE_MANY_EVENTS = "raise-many-events"
KEY_CREATE_APPLICATION = "create-application"
KEY_CLOSE_APPLICATION = "close-application"
KEY_FIRE_CONSTRUCTOR_CALLBACK = "fire-constructor-callback"
KEY_CLOSE_WINDOW = "action\":\"close-window"
KEY_CONSOLE_LOG = "INFO:CONSOLE"
KEY_IGNORE_LICENSE_KEY = "\"WARNING : Application does not have a valid OpenFin license key implemented"
KEY_RECEIVED_IN_RUNTIME = "received in-runtime:"
KEY_RECEIVED_IN_RUNTIME_SYNC = "received in-runtime-sync :"
KEY_RECEIVED_EXTERNAL = "received external-adapter"
KEY_SENT_IN_RUNTIME = "sent in-runtime"

## Arguments
# By default, the diagnostics parser will take a debug.log file in the same directory, print basic information and errors to the console, 
# and output a debug_parsed.json file including all of the received logs.

parser = argparse.ArgumentParser(description="Takes debug.log and constructs standard JSON.")
parser.add_argument('--logpath', help='path full/relative to debug.log file')
parser.add_argument('--outpath', help='path to output parsed log file to')
parser.add_argument('--noconsole', help='Don\'t print to console', action='store_true')
parser.add_argument('--noeventlogs', help='Don\'t include any event logs in output JSON', action='store_true')
parser.add_argument('--noexternallogs', help='Don\'t include external adapter event logs in output JSON', action='store_true')
parser.add_argument('--includesentlogs', help='Include sent in-runtime event logs in output JSON', action='store_true')
parser.add_argument('--noentitylogs', help='Don\'t include logs grouped by entity in output JSON', action='store_true')
parser.add_argument('--norenderlogs', help='Don\'t include logs grouped by render frame ID in output JSON', action='store_true')
args = parser.parse_args()


class ParseDebugLog(object):
    """ Takes debug.log and constructs standard JSON. """

    def __init__(self):
        self.start_time = int(round(time.time() * 1000))
        self.debug_json = {}
        self.process_versions = {}
        self.applications = []
        self.entities = {}
        self.render_frames = {}
        self.console_logs = []
        self.other_errors = []
        self.render_frame_logs = {}
        self.entity_logs = {}

    def execute(self):
        """ Main function for class. """
        log_lines = self.load_debug_log()
        self.parse_log_lines(log_lines)
        self.write_debug_json()
        if not args.noconsole:
            self.print_to_console()
        self.print_time_to_execute()

    def load_debug_log(self):
        """ Reads debug.log into a list of the log lines in memory. """
        debug_log_file_path = DEFAULT_DEBUG_LOG_FILE_PATH
        if args.logpath:
            debug_log_file_path = args.logpath
        print("Reading Log: %s" % os.path.abspath(debug_log_file_path))

        log_lines = []
        with open(debug_log_file_path, 'r') as fp:
            # Collapse multi-line logs into a single line
            for line in fp:
                if line.startswith("["):
                    log_lines.append(line)
                else:
                    log_lines[-1] = log_lines[-1].strip() + line.strip()

        return log_lines

    def parse_log_lines(self, log_lines):
        """ Meat of the script. """

        idx = 0
        while idx < len(log_lines):
            current_line = log_lines[idx]
            message_list = self.get_msg(current_line)
            if len(message_list) < 2:
                # For some reason, there is no timestamp on the message. Skip.
                idx += 1
                continue
            message_split = message_list[1].split(')] ', 1)
            if len(message_split) < 2:
                # handles weird things like form signature and histograms
                idx += 1
                continue
            timestamp = message_list[0]
            message_log_level = message_split[0]
            message_str = message_split[1]

            if message_str.startswith(KEY_PROCESS_VERSIONS):
                # Capture runtime info
                self.process_versions = eval(message_str[18:])
            elif message_log_level.startswith(KEY_CONSOLE_LOG):
                # Grabs all console logs
                if not message_str.startswith(KEY_IGNORE_LICENSE_KEY):
                    # Trims out license key logs. Lots of noise.
                    self.console_logs.append(log_lines[idx])
            elif message_str.startswith("{"):
                # Grabs application launches and errors
                if message_str.startswith("{\"stack\":\"TypeError"):
                    self.other_errors.append(log_lines[idx])
                elif ("\"runtime\":") in message_str:
                    app_info = json.loads(message_str)
                    self.applications.append(app_info)
            elif message_str.startswith(KEY_RECEIVED_IN_RUNTIME):
                # Grabs all normal events, also tracks entity creation
                self.handle_received_in_runtime_events(
                    message_str, timestamp, current_line)
            elif not args.noeventlogs:
                # Grabs all sync and external events
                self.handle_extraneous_events(
                    message_str, timestamp, current_line)

            idx += 1
        return  # parse_log_lines

    def get_msg(self, s):
        return s.strip()[1:].split(']-[', 1)

    def handle_received_in_runtime_events(self, message_str, timestamp, current_line):
        """ Grabs all normal events, also tracks entity creation """
        render_frame_id = re.search(
            r'(?<=runtime: )(.*?)(?= \[)', message_str).group()
        if KEY_RAISE_MANY_EVENTS in message_str:
            json_str = re.sub(r'^.*?{', '{', message_str)
            window_info = json.loads(json_str)
            entity_info = window_info["payload"][0][1]

            # TODO: This timestamp is for raise-many-events, maybe tag to window-create-window?
            entity_info['time_started'] = timestamp
            # Add entity info, grouped by uuid/name
            uuid_group = self.entities.setdefault(entity_info["uuid"], {})
            uuid_group[entity_info["name"]] = entity_info
            # Add entity info, grouped by render_frame_id
            render_frame_group = self.render_frames.setdefault(render_frame_id, {})
            render_frame_group[entity_info["name"]] = entity_info
        if KEY_FIRE_CONSTRUCTOR_CALLBACK in message_str:
            # Adam found that some windows came up without a time_started. Seems like it happens when raise-many-events doesn't get hit. 
            # TODO: Looks like we can get a time_created from fire-constructor-callback listen though, although it's probably not reliable
            json_str = re.sub(r'^.*?{', '{', message_str)
            window_info = json.loads(json_str)
            entity_info = window_info["payload"]

            entity_info['time_started'] = timestamp
            # Add entity info, grouped by uuid/name
            uuid_group = self.entities.setdefault(entity_info["uuid"], {})
            uuid_group[entity_info["name"]] = entity_info
            # Add entity info, grouped by render_frame_id
            render_frame_group = self.render_frames.setdefault(render_frame_id, {})
            render_frame_group[entity_info["name"]] = entity_info

        elif KEY_CREATE_APPLICATION in message_str:
            json_str = re.sub(r'^.*?{', '{', message_str)
            app_info = json.loads(json_str)
            self.applications.append(app_info)
        elif KEY_CLOSE_APPLICATION in message_str:
            json_str = re.sub(r'^.*?{', '{', message_str)
            app_info = json.loads(json_str)
            uuid = app_info["payload"]["uuid"]
            uuid_group = self.entities.setdefault(uuid, {})
            name_group = uuid_group.setdefault(uuid, app_info)
            name_group["time_ended"] = timestamp
        elif KEY_CLOSE_WINDOW in message_str:
            json_str = re.sub(r'^.*?{', '{', message_str)
            window_info = json.loads(json_str)
            uuid = window_info["payload"]["uuid"]
            name = window_info["payload"]["name"]
            uuid_group = self.entities.setdefault(uuid, {})
            name_group = uuid_group.setdefault(name, window_info)
            name_group["time_ended"] = timestamp

        # finally, after tracking launches and closes, map the event log to entities and render frames:
        if not args.noeventlogs:
            if not args.norenderlogs:
                render_frame_log_group = self.render_frame_logs.setdefault(render_frame_id, [])
                render_frame_log_group.append(current_line)

            if not args.noentitylogs:
                identity = re.findall(r'\[(.*?)\]', message_str)
                uuid = identity[0]
                name = identity[1]
                uuid_group = self.entity_logs.setdefault(uuid, {})
                name_group = uuid_group.setdefault(name, [])
                name_group.append(current_line)
        return  # handle_received_in_runtime_events

    def handle_extraneous_events(self, message_str, timestamp, current_line):
        """ Grabs all sync and external events """
        if message_str.startswith(KEY_RECEIVED_IN_RUNTIME_SYNC):
            if not args.norenderlogs:
                # TODO: Is this a render frame ID or nah? What is this number?
                render_frame_id = re.search(
                    r'(?<=received in-runtime-sync : )(.*?)(?= \[)', message_str).group()
                render_frame_log_group = self.render_frame_logs.setdefault(render_frame_id, [])
                render_frame_log_group.append(current_line)

            if not args.noentitylogs:
                identity = re.findall(r"\[(.*?)\]", message_str)
                uuid = identity[0]
                name = identity[1]
                uuid_group = self.entity_logs.setdefault(uuid, {})
                name_group = uuid_group.setdefault(name, [])
                name_group.append(current_line)
        elif not args.noexternallogs and not args.norenderlogs and message_str.startswith(KEY_RECEIVED_EXTERNAL):
            # TODO: Is this a render frame ID or nah? What is this number?
            render_frame_id = re.search(
                r'(?<=received external-adapter <= )(.*?)(?= \{)', message_str).group()
            render_frame_log_group = self.render_frame_logs.setdefault(render_frame_id, [])
            render_frame_log_group.append(current_line)

        # TODO: Do we want to add the sent-in-runtime events? It significantly increases the file size, but there may be relevant payloads we want in there.
        elif args.includesentlogs and not args.norenderlogs and message_str.startswith(KEY_SENT_IN_RUNTIME):
            render_frame_id = re.search(
                r'(?<=sent in-runtime <= )(.*?)(?= \{)', message_str).group()
            render_frame_log_group = self.render_frame_logs.setdefault(render_frame_id, [])
            render_frame_log_group.append(current_line)
        return  # handle_extraneous_events

    def print_to_console(self):
        print("\n--------------------XXX--------------------")

        print("\nProcess Versions:")
        print("\n")
        pprint.pprint(self.process_versions)

        print("\n--------------------XXX--------------------")

        print("\nApplications:")
        for idx, application in enumerate(self.applications):
            print("\n")
            print(f"Application #{idx + 1}")
            pprint.pprint(application)

        print("\n--------------------XXX--------------------")

        print("\nEntities:")
        print("Entities sorted by time_started")

        # Sorting function to put entities in order of time started
        def by_time_started(item):
            return item['time_started']

        for application_dict_key in self.entities:
            print("\n")
            print("\n")
            print(f"Application UUID: {application_dict_key}")
            application_dict = self.entities[application_dict_key]
            for idx, value in enumerate(sorted(application_dict.values(), key=by_time_started)):
                print("\n")
                print(f"Entity #{idx + 1} for {application_dict_key}: ")
                pprint.pprint(value)

        print("\n--------------------XXX--------------------")

        print("\nEntities by Render Frame ID:")
        print("Entities sorted by time_started")

        for render_frame_id in self.render_frames:
            print("\n")
            print("\n")
            print(f"Render Frame ID: {render_frame_id}")
            render_frame_dict = self.render_frames[render_frame_id]
            for idx, value in enumerate(sorted(render_frame_dict.values(), key=by_time_started)):
                print("\n")
                print(f"Entity #{idx + 1} for {render_frame_id}: ")
                pprint.pprint(value)

        print("\n--------------------XXX--------------------")

        print("\nConsole Logs:")
        for idx, console_log in enumerate(self.console_logs):
            print("\n")
            print(f"Console Log #{idx + 1}")
            print(console_log)

        print("\n--------------------XXX--------------------")

        print("\nOther Errors:")
        for idx, other_error in enumerate(self.other_errors):
            print("\n")
            print(f"Error #{idx + 1}")
            pprint.pprint(other_error)

        print("\n--------------------XXX--------------------")
        return  # print_to_console

    def write_debug_json(self):
        """ Writes self.debug_json to file. """

        self.debug_json['process_versions'] = self.process_versions
        self.debug_json['applications'] = self.applications
        self.debug_json['entities'] = self.entities
        self.debug_json['render_frames'] = self.render_frames
        self.debug_json['console_logs'] = self.console_logs
        self.debug_json['other_errors'] = self.other_errors
        self.debug_json['render_frame_logs'] = self.render_frame_logs
        self.debug_json['entity_logs'] = self.entity_logs

        out_path = DEFAULT_DEBUG_LOG_OUT_PATH
        if args.outpath:
            out_path = args.outpath
        with open(out_path, 'w') as outfile:
            json.dump(self.debug_json, outfile, indent=2, sort_keys=True)
        print("Wrote debug_json to file: %s" % os.path.abspath(out_path))

    def print_time_to_execute(self):
        end_time = int(round(time.time() * 1000))

        print("\nParser Start Time =", self.start_time)
        print("Parser End Time =", end_time)
        print("Parser ms taken:", end_time - self.start_time)


def main():
    parser = ParseDebugLog()
    parser.execute()


if __name__ == '__main__':
    main()