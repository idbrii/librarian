#! /usr/bin/env python3

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import configparser
import os
import shutil
import subprocess

import git


ROOT_PATH = os.path.expanduser("~/.librarian/")
CONFIG_PATH = os.path.join(ROOT_PATH, "config.ini")
CLONES_PATH = os.path.join(ROOT_PATH, "clones/")


def _get_args():
    """Program arguments

    librarian config love --path src/lib/
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
    archive.add_argument('--include',
                         default='',
                         help='Included files')

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


def _copy_and_overwrite(from_path, to_path):
    if os.path.exists(to_path):
        shutil.rmtree(to_path)
    shutil.copytree(from_path, to_path, ignore=shutil.ignore_patterns('.git'))


def add_module(module, kind, module_path, target_repo_path, target_path):
    target_repo = git.Repo(target_repo_path)
    if target_repo.is_dirty():
        print('Failed to add module {}. Target repo is dirty:\n{}'.format(module, target_repo_path))
        print(target_repo.git.status())
        return

    dst = target_path.replace(os.path.expanduser('~'), '~', 1)
    print('Copying {0} module "{1}" into {2}'.format(kind, module, dst))
    src_repo = git.Repo(module_path)
    master = src_repo.remotes.origin.refs.master
    branch = src_repo.create_head(module, master).set_tracking_branch(master)
    _copy_and_overwrite(module_path, target_path)


def main():
    # HACK
    os.chdir(os.path.expanduser('~/data/code/game/puppypark/'))

    os.makedirs(CLONES_PATH, exist_ok=True)
    config = _read_config()
    args = _get_args()
    if   args.action == 'config':
        try:
            config.add_section(args.kind)
            section = config[args.kind]
        except configparser.DuplicateSectionError:
            section = config[args.kind]
            print('''Kind '{}' already registered:
    lib_path: {} -> {}
    include: {} -> {}
            '''.format(args.kind,
                       section.get('LIB_PATH', '<none>'), args.path,
                       section.get('INCLUDE', '<none>'), args.include))
        section['LIB_PATH'] = args.path
        section['INCLUDE'] = args.include

    elif args.action == 'archive':
        # librarian archive love windfield https://github.com/adnzzzzZ/windfield.git
        clone_path = os.path.join(CLONES_PATH, args.module)
        repo = git.Repo.init(clone_path)
        try:
            config.add_section(args.module)
            section = config[args.module]

            section['KIND'] = args.kind
            section['CLONE'] = clone_path
            print('Cloning "{}" module "{}" into Library...'.format(args.kind, args.module))
            origin = repo.create_remote('origin', args.clone_url)

        except configparser.DuplicateSectionError:
            section = config[args.module]
            print('''Module '{}' already registered:
    kind: {}
    checkout: {}
            '''.format(args.module,
                       section['KIND'],
                       section['CLONE']))

        origin = repo.remotes.origin
        assert(origin.exists())
        print('Updating module "{}" to latest...'.format(args.module))
        origin.fetch()
        master = repo.create_head('master', origin.refs.master).set_tracking_branch(origin.refs.master)
        master.checkout()
        print(master.commit.message)

    elif args.action == 'add':
        # librarian add puppypark windfield
        clone_path = config[args.module]['CLONE']
        working_dir = os.getcwd()
        kind = config[args.module]['KIND']
        target_path = os.path.join(working_dir, config[kind]['LIB_PATH'], args.module)
        add_module(args.module,
                   config[args.module]['KIND'],
                   config[args.module]['CLONE'],
                   working_dir,
                   target_path)

    elif args.action == 'sync':
        # librarian sync puppypark windfield
        clone_path = config[args.module]['CLONE']
        repo = git.Repo(clone_path)
        if repo.is_dirty():
            print('Failed to copy changes from project {}. Target repo is dirty:\n{}'.format(args.project, clone_path))
            print(repo.git.status())
            return
        print('Copying changes from project "{}" into module "{}"...'.format(args.project, args.module))
        repo.heads[args.module].checkout()
        print("TODO: copy files")

    _write_config(config)


if __name__ == "__main__":
    main()