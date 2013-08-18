# -*- coding: utf-8 -*-

import sublime
import sublime_plugin
import functools
import threading
import subprocess
import time
import re
import os
import commands
import webbrowser

ss_build_process = None


def exec_with_subprocess(command):
    return subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)


def main_thread(callback, *args, **kwargs):
    # sublime.set_timeout gets used to send things onto the main thread
    # most sublime.[something] calls need to be on the main thread
    sublime.set_timeout(functools.partial(callback, *args, **kwargs), 0)


def st2_output(output_view, output):
    if output == "":
        return

    try:
        output_view.set_read_only(False)
        edit = output_view.begin_edit()
        output_view.insert(edit, output_view.size(), output)
        output_view.show(output_view.size())
        output_view.end_edit(edit)
        output_view.set_read_only(True)
    except:
        print("ERROR:Can't output to ST2!!")


class BuildTask(threading.Thread):

    __tasks = []
    __stop = False
    __current_task = None

    def __init__(self, tasks):
        threading.Thread.__init__(self)
        tasks.reverse()
        self.__tasks = tasks

    def run(self):
        try:
            if len(self.__tasks) == 0:
                return

            self.__current_task = self.__tasks.pop()
            if self.__current_task != []:
                while True:
                    if self.__stop is True:
                        break
                    self.__current_task.start()
                    self.__current_task.join()
                    if self.__current_task is None:
                        break

                    if self.__tasks != []:
                        print "Next task"
                        self.__current_task = self.__tasks.pop()
                    else:
                        break
                    time.sleep(0.01)

            print "Finish BuildThread"
        except:
            self.stop()
            main_thread(sublime.message_dialog,
                        'Exception Build Error')

    def stop(self):
        self.__stop = True
        if self.__current_task is not None:
            self.__current_task.kill()
            self.__current_task = None

        print "Stop BuildThread"


def save_settings(key, value):
    s = sublime.load_settings("slideshow.sublime-settings")
    if s:
        s.set(key, value)
        sublime.save_settings("slideshow.sublime-settings")


def load_settings(key, default_value):
    s = sublime.load_settings("slideshow.sublime-settings")
    if s and s.has(key):
        return s.get(key)
    save_settings(key, default_value)
    return default_value


def get_gem_bin_path():
    env = commands.getoutput('gem env')
    rgx_gem_bin = re.compile(r'EXECUTABLE DIRECTORY: ([a-zA-Z\/0-9\.\-]+)')
    result = rgx_gem_bin.search(env)
    if result:
        return result.group(1)
    return None


def setup_gem_path():
    path = get_gem_bin_path()
    if path:
        os.environ['PATH'] += ":" + path


def get_slideshow_templates():
    lists = commands.getoutput('slideshow list')
    lines = lists.split('\n')
    re_template = re.compile(r'\s+([a-zA-Z1-9]+) \(.+\)')
    re_template_list = re.compile(r'Installed template packs in search path')
    template_name = ""
    is_template_lists = False
    templates = []
    for line in lines:
        if is_template_lists == False and re_template_list.match(line):
            is_template_lists = True
        else:
            if is_template_lists == False:
                continue

        if re_template.match(line):
            result = re_template.search(line)
            template_name = result.group(1)
            templates.append(template_name)
    return templates


class Slideshow(sublime_plugin.ApplicationCommand):

    def run(self, command):
        if command == "select_template":
            setup_gem_path()
            self.installed_templates = get_slideshow_templates()
            if self.installed_templates != []:
                sublime.active_window().show_quick_panel(
                    self.installed_templates, self.select_template)

        if command == "build":
            filename = sublime.active_window().active_view().file_name()
            dir = os.path.dirname(filename)
            os.chdir(dir)
            builder = SlideshowBuildTool(filename)
            build_task = BuildTask([builder])
            build_task.start()

    def select_template(self, select):
        global configuration
        if select < 0:
            return
        template = self.installed_templates[select]
        sublime.status_message("slideshow:[" + template + "]")
        save_settings("template", template)


class SlideshowBuildTool(threading.Thread):

    def __init__(self, filename):

        threading.Thread.__init__(self)

        self.setup()
        self.output_view = sublime.active_window().get_output_panel("sspanel")
        sublime.active_window().run_command("show_panel",
                                            {"panel": "output.sspanel"})

        self.template = load_settings("template", "")
        self.file = filename
        self.dir = os.path.dirname(self.file)
        if self.template != "":
            self.command = "slideshow build -t %(template)s"\
                           " %(file)s" % {
                               'template': self.template,
                               'file': self.file
                           }
        else:
            self.command = "slideshow build %(file)s" % {
                'file': self.file
            }

    def get_gem_bin_path(self):
        env = commands.getoutput('gem env')
        rgx_gem_bin = re.compile(r'EXECUTABLE DIRECTORY: ([a-zA-Z\/0-9\.\-]+)')
        result = rgx_gem_bin.search(env)
        if result:
            return result.group(1)
        return None

    def setup(self):
        path = self.get_gem_bin_path()
        if path:
            os.environ['PATH'] += ":" + path
            os.environ['LANG'] = "ja_JP.UTF-8"

    def output(self, message):
        main_thread(st2_output, self.output_view, message)

    def run(self):
        global ss_build_process
        self.output("SlideShow building...\n")
        if ss_build_process and ss_build_process.poll() is None:
            self.output("SlideShowBuild Process is running")
            ss_build_process.kill()
            ss_build_process = None

        command = self.command.encode("utf-8").split()
        ss_build_process = exec_with_subprocess(command)
        result, error = ss_build_process.communicate()
        print(result)
        print(error)
        fname,ext = os.path.splitext(self.file)
        htmlfilename = fname + ".html"
        webbrowser.open(htmlfilename)

    def kill(self):
        global ss_build_process
        self.output("[SlideShow]Kill Process\n")
        if ss_build_process and ss_build_process.poll() is None:
            self.output("Slideshow Build Process is running")
            ss_build_process.kill()
            while ss_build_process.poll() is None:
                time.sleep(0.1)
            ss_build_process = None
