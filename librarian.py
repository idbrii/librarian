#! /usr/bin/env python3

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import configparser
import os
import pprint as pretty
import re
import shutil
import subprocess
import sys

import git


ROOT_PATH = os.path.expanduser("~/.librarian/")
CONFIG_PATH = os.path.join(ROOT_PATH, "config.ini")
CLONES_PATH = os.path.join(ROOT_PATH, "clones/")


def _get_args():
    """Program arguments

    librarian config love --path src/lib/ --root-marker init.lua --rename-single-file-root-marker ".*.lua" --include-pattern ".*.lua|LICENSE.*"
    librarian archive love windfield https://github.com/adnzzzzZ/windfield.git
    librarian add puppypark windfield
    librarian sync puppypark windfield

    _get_args() -> Namespace
    """
    parser = argparse.ArgumentParser(prog='librarian')
    subparsers = parser.add_subparsers(dest='action',
                                       help='Deploy and track changes to modules in your projects.')

    archive = subparsers.add_parser('config',
                                    help='Configure a project kind: a category of projects that define how their managed.')
    archive.add_argument('kind',
                         help='The category of module (what kind of project will it be used in).')
    archive.add_argument('--path',
                         default='',
                         help='The path from the project repo root where modules are added. ex: src/lib/')
    archive.add_argument('--include-pattern',
                         default='',
                         help='Regular expression of files to include when copying to project. If not provided, all files are included.')
    archive.add_argument('--exclude-pattern',
                         default='',
                         help='Regular expression of files to exclude when copying to project. If not provided, all files are included.')
    archive.add_argument('--root-marker',
                         default='',
                         help='A file that indicates the root of the module (may not be the root of the repo). Useful to ignore tests and example code in well-organized repos.')
    archive.add_argument('--rename-single-file-root-marker',
                         default='',
                         help='If there is no root marker but there is a single file matching this regex, then rename it to the root marker.')

    archive = subparsers.add_parser('archive',
                                    help='Add a module to the Library.')
    archive.add_argument('kind',
                         help='The category of module (what kind of project will it be used in).')
    archive.add_argument('module',
                         help='Add a module to your project.')
    archive.add_argument('clone_url',
                         metavar='clone-url',
                         help='The git origin URL to clone from.')

    add = subparsers.add_parser('add',
                                help='Add a module to your project.')
    add.add_argument('project',
                     help='The project to use.')
    add.add_argument('module',
                     help='The module to operate on.')

    sync = subparsers.add_parser('sync',
                                 help='Copy changes to a module from your project to the Library.')
    sync.add_argument('project',
                      help='The project to use.')
    sync.add_argument('module',
                      help='The module to operate on.')

    return parser.parse_args()


def _read_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def _write_config(config):
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)


def _apply_config(args, config):
    try:
        config.add_section(args.kind)
        section = config[args.kind]
        print("Added new kind '{}'.".format(args.kind))
    except configparser.DuplicateSectionError:
        section = config[args.kind]
        print('''Kind '{}' already registered:
path: {} -> {}
include-pattern: {} -> {}
exclude-pattern: {} -> {}
root-marker: {} -> {}
rename-single-file-root-marker: {} -> {}
        '''.format(args.kind,
                   section.get('LIB_PATH', '<none>'), args.path,
                   section.get('INCLUDE_PATTERN', '<none>'), args.include_pattern,
                   section.get('EXCLUDE_PATTERN', '<none>'), args.exclude_pattern,
                   section.get('ROOT_MARKER', '<none>'), args.root_marker,
                   section.get('RENAME_ROOT_MARKER_PATTERN', '<none>'), args.rename_single_file_root_marker))
    has_data = (len(args.path) > 0
        or len(args.include_pattern) > 0
        or len(args.exclude_pattern) > 0
        or len(args.root_marker) > 0)
    if has_data:
        section['LIB_PATH'] = args.path
        section['INCLUDE_PATTERN'] = args.include_pattern
        section['EXCLUDE_PATTERN'] = args.exclude_pattern
        section['ROOT_MARKER'] = args.root_marker
        section['RENAME_ROOT_MARKER_PATTERN'] = str(args.rename_single_file_root_marker)
    else:
        # we just outputted the last data. Good enough for now.
        print('No config changes written.')

def _archive_module(args, config):
    # librarian archive love windfield https://github.com/adnzzzzZ/windfield.git
    clone_path = os.path.join(CLONES_PATH, args.module)
    repo = git.Repo.init(clone_path)
    try:
        config.add_section(args.module)
        section = config[args.module]

        section['KIND'] = args.kind
        section['CLONE'] = clone_path

    except configparser.DuplicateSectionError:
        section = config[args.module]
        print('''Module '{}' already registered:
kind: {}
checkout: {}
        '''.format(args.module,
                   section['KIND'],
                   section['CLONE']))

    try:
        origin = repo.remotes.origin
    except AttributeError:
        print('Cloning "{}" module "{}" into Library...'.format(args.kind, args.module))
        origin = repo.create_remote('origin', args.clone_url)

    assert(origin.exists())
    print('Updating module "{}" to latest...'.format(args.module))
    origin.fetch()
    master = repo.create_head('master', origin.refs.master).set_tracking_branch(origin.refs.master)
    master.checkout()
    print('\tCommit: {}\n\tMessage: "{}"'.format(master.commit.hexsha, master.commit.message.strip()))


def _find_src_module_path(path, root_marker, should_include_fn):
    """Find where the include-able module starts.

    _find_src_module_path(str, str, function) -> str
    """
    first_includeable = []
    for dirpath,dirs,files in os.walk(path, topdown=True):
        markers = [dirpath for f in files if f == root_marker]
        if markers:
            return markers[0]
        if not first_includeable:
            first_includeable = [dirpath for f in files if should_include_fn(f)]

    # no marker found
    if first_includeable:
        return first_includeable[0]
    else:
        print('Failed to file includable files in {}! Aborting...'.format(path))
        sys.exit(-2)


def _copy_and_overwrite(from_path, to_path, should_include_fn):
    print('Copying {} to {}'.format(from_path, to_path))
    if os.path.exists(to_path):
        shutil.rmtree(to_path)
    def ignore(dir_path, items):
        return [f for f in items if not should_include_fn(f)]
    shutil.copytree(from_path, to_path, ignore=ignore)


def _rename_if_single_file(path, new_name, include_re):
    """If there's only a single file in 'path', rename it to new_name.

    _rename_if_single_file(str, str) -> None
    """
    file = None
    for dirpath,dirs,files in os.walk(path, topdown=True):
        if include_re:
            files = [f for f in files if include_re.match(f)]
        if not dirs and len(files) == 1:
            f = files[0]
            src = os.path.join(dirpath, f)
            dst = os.path.join(dirpath, new_name)
            shutil.move(src, dst)
        # either way, return. We don't need to go deeper.
        return


def _add_module(args, config):
    # librarian add puppypark windfield
    target_repo_path = _get_project_dir(args.project)
    kind             = config[args.module]['KIND']
    target_path      = os.path.join(target_repo_path, config[kind]['LIB_PATH'], args.module)
    project          = args.project
    module           = args.module
    module_path      = config[args.module]['CLONE']
    cfg              = config[kind]
    target_repo      = git.Repo(target_repo_path)

    if target_repo.is_dirty():
        print('Failed to add module {}. Target repo is dirty:\n{}'.format(module, target_repo_path))
        print(target_repo.git.status())
        return

    dst = target_path.replace(os.path.expanduser('~'), '~', 1)
    print('Copying {0} module "{1}" into {2}'.format(kind, module, dst))
    src_repo = git.Repo(module_path)
    master = src_repo.remotes.origin.refs.master
    branch = src_repo.create_head(project, master).set_tracking_branch(master)
    print('Created branch "{}" in library for module "{}".'.format(project, module))

    include_re = None
    exclude_re = None
    if len(cfg['INCLUDE_PATTERN']) > 0:
        include_re = re.compile(cfg['INCLUDE_PATTERN'])
    if len(cfg['EXCLUDE_PATTERN']) > 0:
        exclude_re = re.compile(cfg['EXCLUDE_PATTERN'])

    if include_re is None and exclude_re is None:
        def should_include(f):
            return f != '.git'
    else:
        def should_include(f):
            return (f != '.git'
                    and (include_re is None or include_re.match(f))
                    and (exclude_re is None or exclude_re.match(f) is None))

    root_marker = cfg['ROOT_MARKER']
    module_path = _find_src_module_path(module_path, root_marker, should_include)
    _copy_and_overwrite(module_path, target_path, should_include)
    single = cfg['RENAME_ROOT_MARKER_PATTERN']
    if single:
        _rename_if_single_file(target_path, root_marker, re.compile(single))


def sync_module(project, module, module_repo_path, src_path, cfg):
    repo = git.Repo(module_repo_path)
    if repo.is_dirty():
        print('Failed to sync module {}. module repo is dirty:\n{}'.format(module, module_repo_path))
        print(repo.git.status())
        return

    dst = src_path.replace(os.path.expanduser('~'), '~', 1)
    try:
        repo.heads[project].checkout()
    except IndexError:
        print("ERROR: Branch '{}' doesn't exist in library for module '{}'. Have you run `librarian add {} {}`?".format(project, module, project, module))
        sys.exit(-1)

    print('Copying module "{}" from {}'.format(module, dst))

    include_re = None
    exclude_re = None
    if len(cfg['INCLUDE_PATTERN']) > 0:
        include_re = re.compile(cfg['INCLUDE_PATTERN'])
    if len(cfg['EXCLUDE_PATTERN']) > 0:
        exclude_re = re.compile(cfg['EXCLUDE_PATTERN'])

    if include_re is None and exclude_re is None:
        def should_include(f):
            return f != '.git'
    else:
        def should_include(f):
            return (f != '.git'
                    and (include_re is None or include_re.match(f))
                    and (exclude_re is None or exclude_re.match(f) is None))

    root_marker = cfg['ROOT_MARKER']
    dst_path = _find_src_module_path(module_repo_path, root_marker, should_include)

    restore_git = None
    if dst_path == module_repo_path:
        # If we're operating on the top-level, then we need to save our .git
        # folder!
        dot_git = os.path.join(dst_path, '.git')
        temp_git = os.path.join(dst_path, '..', '.git')
        shutil.move(dot_git, temp_git)
        def restore_git():
            shutil.move(temp_git, dot_git)

    _copy_and_overwrite(src_path, dst_path, should_include)
    single = cfg['RENAME_ROOT_MARKER_PATTERN']
    if single:
        _rename_if_single_file(dst_path, single.replace('.*', module), re.compile(single))
    if restore_git:
        restore_git()


def _get_project_dir(project):
    """Get the current project's directory.

    It's just the current working directory, but we do some validation to
    ensure you're not running from the wrong location.

    _get_project_dir() -> str
    """
    working_dir = os.getcwd()
    if working_dir.find(project) < 0:
        print("Current path ({}) doesn't contain name of project '{}'.".format(working_dir, args.project))
        answer = input("Are you in the right place? ")
        if answer.lower()[0] != 'y':
            sys.exit(-1)
    return working_dir


def main():
    # HACK
    os.chdir(os.path.expanduser('~/data/code/game/puppypark/'))

    os.makedirs(CLONES_PATH, exist_ok=True)
    config = _read_config()
    args = _get_args()
    if   args.action == 'config':
        _apply_config(args, config)

    elif args.action == 'archive':
        _archive_module(args, config)

    elif args.action == 'add':
        _add_module(args, config)

    elif args.action == 'sync':
        # librarian sync puppypark windfield
        kind = config[args.module]['KIND']
        working_dir = _get_project_dir(args.project)
        target_path = os.path.join(working_dir, config[kind]['LIB_PATH'], args.module)
        sync_module(args.project,
                    args.module,
                    config[args.module]['CLONE'],
                    target_path,
                    config[kind])


    _write_config(config)


if __name__ == "__main__":
    main()
