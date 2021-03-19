#! /usr/bin/env python3

# Requires gitpython
#   pip3 install gitpython

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
    '''
    _get_args() -> Namespace
    '''

    about = """Librarian automates copying modules to and from projects

Librarian maintains a central Library for your modules. It copies modules
from the Library to your project and you can specify which kinds of files
you want included so you can skip demos/examples and tests. Librarian can
copy modules back to the Library from your project so you can contribute
them upstream or use them in other projects.

Librarian is an alternative to git submodules. Instead of putting creating
your own forks of git repos, granting access to your developers, and adding
submodules to your project, you can use librarian to clone the remote, copy
the files into your project, and copy changes back into your clone.

Example:

Create a 'love' config in librarian for lua projects that renames single
file libraries so they exist in a folder, but can still be imported by
name:
    librarian config love --path src/lib/ --root-marker init.lua --rename-single-file-root-marker ".*.lua" --include-pattern ".*.lua|LICENSE.*|README.*" --exclude-pattern "main.lua|demos?|example.*|tests?|spec"

Register a 'love' module 'windfield':
    librarian acquire love windfield https://github.com/adnzzzzZ/windfield.git

Copy our 'love' module 'windfield' to a project 'puppypark':
    librarian checkout puppypark windfield

Copy changes in project 'puppypark' from module 'windfield' back to the Library:
    librarian checkin puppypark windfield

Get updates to Library module 'windfield' from remote:
    librarian pull windfield

List all 'love' modules:
    librarian list --kind love
    """
    parser = argparse.ArgumentParser(prog='librarian',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=about)
    subparsers = parser.add_subparsers(dest='action',
                                       help='Deploy and track changes to modules in your projects.')

    acquire = subparsers.add_parser('config',
                                    help='Configure a project kind: a category of projects that define how their managed.')
    acquire.add_argument('kind',
                         help='The category of module (what kind of project will it be used in).')
    acquire.add_argument('--path',
                         default='',
                         help='The path from the project repo root where modules are added. ex: src/lib/')
    acquire.add_argument('--include-pattern',
                         default='',
                         help='Regular expression of files to include when copying to project. If not provided, all files are included.')
    acquire.add_argument('--exclude-pattern',
                         default='',
                         help='Regular expression of files to exclude when copying to project. If not provided, all files are included.')
    acquire.add_argument('--root-marker',
                         default='',
                         help='A file that indicates the root of the module (may not be the root of the repo). Useful to ignore tests and example code in well-organized repos.')
    acquire.add_argument('--rename-single-file-root-marker',
                         default='',
                         help='If there is no root marker but there is a single file matching this regex, then rename it to the root marker.')

    acquire = subparsers.add_parser('acquire',
                                    help='Add a module to the Library to later checkout into a project.')
    acquire.add_argument('kind',
                         help='The category of module (what kind of project will it be used in).')

    # TODO: Consider providing a deploy name option? So penlight is the name and pl is the destination folder.
    acquire.add_argument('module',
                         help='The module to begin tracking in the Library. This name will be used to deploy the module in projects.')
    acquire.add_argument('clone_url',
                         metavar='clone-url',
                         help='The git origin URL to clone from.')

    ls = subparsers.add_parser('list',
                                 help='List modules in your Library.')
    ls.add_argument('--kind',
                      help='The kind of modules to list. Without this argument, list modules of every kind.')

    pull = subparsers.add_parser('pull',
                                 help='Update your Library copy of a module.')
    pull.add_argument('--remote',
                      help="The remote to pull changes from. Defaults to 'origin' or the remote if there's only one remote.")
    pull.add_argument('module',
                      help='The module to update with latest from its git remote.')

    checkout = subparsers.add_parser('checkout',
                                help='Export a module into your project.')
    checkout.add_argument('project',
                     help='The project to use.')
    checkout.add_argument('module',
                     help='The module to copy into your project.')

    checkin = subparsers.add_parser('checkin',
                                 help='Copy changes to a module from your project back to the Library.')
    checkin.add_argument('project',
                      help='The project to use.')
    checkin.add_argument('module',
                      help='The module to copy from your project to the Library.')

    return parser.parse_args()


def _read_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def _write_config(config):
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)


def _get_master_from_remote(remote):
    try:
        return remote.refs.master
    except AttributeError as e:
        return remote.refs.main


def _get_remote_or_bail(repo, name):
    """Get remote by name.
    name may be None.

    _get_remote_or_bail(Repo, str) -> Remote
    """
    remote_name = name
    if not remote_name:
        # Default to origin since it's the convention.
        remote_name = 'origin'
    
    try:
        return repo.remote(remote_name)
    except ValueError as e:
        if not name and len(repo.remotes) == 1:
            # Should be safe to use the only remote if it was renamed and user
            # didn't ask for a specific name.
            return repo.remotes[0]
        else:
            print('ERROR:', e)
            sys.exit(1)


def _build_changelog(repo, before_sha, after_sha='HEAD'):
    return repo.git.log(f"{before_sha}..{after_sha}", pretty='  * %s', first_parent=True, reverse=True)


def _apply_config(args, config):
    try:
        config.add_section(args.kind)
        section = config[args.kind]
        print("Added new kind '{}':".format(args.kind))
    except configparser.DuplicateSectionError:
        section = config[args.kind]
        print("Kind '{}' already registered:".format(args.kind))

    changes = '''path: {} -> {}
include-pattern: {} -> {}
exclude-pattern: {} -> {}
root-marker: {} -> {}
rename-single-file-root-marker: {} -> {}
        '''.format(
                   section.get('lib_path', '<none>'), args.path,
                   section.get('include_pattern', '<none>'), args.include_pattern,
                   section.get('exclude_pattern', '<none>'), args.exclude_pattern,
                   section.get('root_marker', '<none>'), args.root_marker,
                   section.get('rename_root_marker_pattern', '<none>'), args.rename_single_file_root_marker)
    has_data = (len(args.path) > 0
        or len(args.include_pattern) > 0
        or len(args.exclude_pattern) > 0
        or len(args.root_marker) > 0)
    if has_data:
        section['lib_path'] = args.path
        section['include_pattern'] = args.include_pattern
        section['exclude_pattern'] = args.exclude_pattern
        section['root_marker'] = args.root_marker
        section['rename_root_marker_pattern'] = str(args.rename_single_file_root_marker)
    else:
        # we just outputted the last data. Good enough for now.
        print('(No config changes written.)')
        changes = changes.replace('->', '')
    print(changes)


def _acquire_module(args, config):
    # librarian acquire love windfield https://github.com/adnzzzzZ/windfield.git
    clone_path = os.path.join(CLONES_PATH, args.module)
    repo = git.Repo.init(clone_path)
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):
        print('Failed to checkout module {}. Target repo is dirty:\n{}'.format(args.module, clone_path))
        print(target_repo.git.status())
        return

    try:
        config.add_section(args.module)
        section = config[args.module]

        section['kind'] = args.kind
        section['clone'] = clone_path
        section['url'] = args.clone_url

    except configparser.DuplicateSectionError:
        section = config[args.module]
        print('''Module '{}' already registered:
kind: {}
checkout: {}
url: {}
        '''.format(args.module,
                   section['kind'],
                   section['clone'],
                   section['url']))

    if len(repo.remotes) > 0:
        print(f'Module "{args.module}" already exists in Library.\nUse "librarian pull {args.module}" to update.')
        return

    print('Cloning "{}" module "{}" into Library...'.format(args.kind, args.module))
    origin = repo.create_remote('origin', args.clone_url)

    assert(origin.exists())
    origin.fetch()
    remote_master = _get_master_from_remote(origin)
    # New branch. All of our branches are named master -- even if remote uses main.
    master = repo.create_head('master', remote_master)
    master.set_tracking_branch(remote_master)

    master.checkout(force=True)
    print('\tCommit: {}\n\tMessage:\n{}\n'.format(master.commit.hexsha, master.commit.message.strip()))


def _list_module(args, config):
    # librarian list --kind love
    want_kind = args.kind
    want_all = want_kind == None
    count = 0
    for c in config:
        try:
            kind = config[c]['kind']
            if want_all or kind == want_kind:
                url = config[c]['url']
                print(f"{c:10}\t\t{kind} module from {url}")
                count += 1
        except KeyError as e:
            # Entry for a kind, not a module.
            pass

    if want_kind:
        print(f"Found {count} {want_kind} modules")
    else:
        print(f"Found {count} modules of any kind")


def _pull_module(args, config):
    # librarian pull --remote origin windfield
    module           = args.module
    try:
        kind         = config[args.module]['kind']
    except KeyError:
        print("ERROR: Module '{0}' doesn't exist in library. Have you run `librarian acquire blah {0} https://blah/{0}`?".format(module))
        sys.exit(-1)
    module_path      = config[args.module]['clone']
    cfg              = config[kind]

    src_repo = git.Repo(module_path)

    if src_repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):
        print('Failed to pull module {}. Library repo is dirty:\n{}'.format(module, module_path))
        print(src_repo.git.status())
        return

    src_repo = git.Repo(module_path)
    local_master = src_repo.refs.master

    origin = _get_remote_or_bail(src_repo, args.remote)

    # All of our branches are named master -- even if remote uses main.
    remote_master = _get_master_from_remote(origin)
    dst = module_path.replace(os.path.expanduser('~'), '~', 1)

    print('Pulling module "{0}" changes from "{1}" into {2}'.format(module, remote_master, dst))
    master = src_repo.branches.master
    before_sha = master.commit.hexsha
    origin.pull(remote_master.remote_head)

    if before_sha != master.commit.hexsha:
        changelog = _build_changelog(src_repo, before_sha)
        print('Changelog:')
        print(changelog)
        print('Latest:')
        print('\tCommit: {}\n\tDate: {}\n  Message:\n{}\n'.format(master.commit.hexsha, master.commit.committed_datetime, master.commit.message.strip()))
    else:
        print('Already up to date.')


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
            first_includeable = [dirpath for f in files if should_include_fn(dirpath, f)]
        dirs[:] = [d for d in dirs if should_include_fn(dirpath, d)]

    # no marker found
    if first_includeable:
        return first_includeable[0]
    else:
        print('Failed to file includable files in {}! Aborting...'.format(path))
        sys.exit(-2)


def _copy_and_overwrite(from_path, to_path, should_include_fn):
    print('Copying {} to {}'.format(from_path, to_path))
    if not os.path.exists(from_path):
        raise FileNotFoundError('No such file or directory: '+ from_path)

    if os.path.exists(to_path):
        shutil.rmtree(to_path)

    def ignore(dir_path, items):
        return [f for f in items if not should_include_fn(dir_path, f)]
    shutil.copytree(from_path, to_path, ignore=ignore)
    _remove_empty_directories(to_path)


def _remove_empty_directories(root):
    for dirpath,dirs,files in os.walk(root, topdown=False):
        for directory in dirs:
            path = os.path.join(dirpath, directory)
            try:
                os.rmdir(path)
            except OSError as ex:
                # Wasn't empty, couldn't delete.
                pass


def _rename_if_single_file(path, new_name, include_re):
    """If there's only a single file in 'path', rename it to new_name.

    _rename_if_single_file(str, str) -> None
    """
    file = None
    for dirpath,dirs,files in os.walk(path, topdown=True):
        if include_re:
            files = [f for f in files if include_re.fullmatch(f)]
        has_relevant_dirs = any(['test' not in d and d != '.git' for d in dirs])
        if not has_relevant_dirs and len(files) == 1:
            file = files[0]
            src = os.path.join(dirpath, file)
            dst = os.path.join(dirpath, new_name)
            shutil.move(src, dst)
        # either way, return. We don't need to go deeper.
        return file


def _include_all(dirpath, f):
    """Like the function returned by _build_should_include, but matches every
    file.
    """
    return True

def _build_should_include(cfg):
    include_re = None
    exclude_re = None
    if len(cfg['include_pattern']) > 0:
        include_re = re.compile(cfg['include_pattern'])
    if len(cfg['exclude_pattern']) > 0:
        exclude_re = re.compile(cfg['exclude_pattern'])

    if include_re is None and exclude_re is None:
        def should_include(dir_path, f):
            return f != '.git'
    else:
        def should_include(dir_path, f):
            return (f != '.git'
                    and (include_re is None or include_re.fullmatch(f) is not None or os.path.isdir(os.path.join(dir_path,f)))
                    and (exclude_re is None or exclude_re.fullmatch(f) is None))
    return include_re, exclude_re, should_include


def _checkout_module(args, config):
    # librarian checkout puppypark windfield
    project          = args.project
    module           = args.module
    try:
        kind         = config[args.module]['kind']
    except KeyError:
        print("ERROR: Module '{0}' doesn't exist in library. Have you run `librarian acquire blah {0} https://blah/{0}`?".format(module))
        sys.exit(-1)
    target_repo_path = _get_project_dir(args.project)
    target_path      = os.path.join(target_repo_path, config[kind]['lib_path'], args.module)
    module_path      = config[args.module]['clone']
    cfg              = config[kind]
    target_repo      = git.Repo(target_repo_path)

    if target_repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):
        print('Failed to checkout module {}. Target repo is dirty:\n{}'.format(module, target_repo_path))
        print(target_repo.git.status())
        return

    dst = target_path.replace(os.path.expanduser('~'), '~', 1)
    print('Copying {0} module "{1}" into {2}'.format(kind, module, dst))
    src_repo = git.Repo(module_path)
    local_master = src_repo.refs.master

    try:
        branch = src_repo.heads[project]
        # Update existing
        branch.set_reference(local_master.commit)
    except IndexError:
        # New branch
        branch = src_repo.create_head(project, local_master).set_tracking_branch(local_master.tracking_branch())
    print('Created branch "{}" in library for module "{}".'.format(project, module))

    include_re,exclude_re,should_include = _build_should_include(cfg)

    root_marker = cfg['root_marker']
    module_path = _find_src_module_path(module_path, root_marker, should_include)
    is_update = os.path.exists(target_path)
    _copy_and_overwrite(module_path, target_path, should_include)
    single = cfg['rename_root_marker_pattern']
    if single:
        renamed = _rename_if_single_file(target_path, root_marker, re.compile(single))
        if renamed:
            config[module]['renamed_root_marker'] = renamed

    if target_repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):
        target_repo.git.add(A=True)
        action = 'Updated' if is_update else 'Added'
        msg = '''Librarian: {1} module {0}
        
{0} is from {2}.
\t{0}@{3}
\tMessage:\n{4}'''.format(module, action, config[args.module]['url'], branch.commit.hexsha, branch.commit.message.strip())
        target_repo.index.commit(msg)
        print('Commit complete:\n'+ msg)
    else:
        print('No changes to apply')


def _checkin_module(args, config):
    # librarian checkin puppypark windfield
    module           = args.module
    project          = args.project
    try:
        kind         = config[args.module]['kind']
    except KeyError:
        print("ERROR: Module '{0}' doesn't exist in library. Have you run `librarian acquire blah {0} https://blah/{0}`?".format(module))
        sys.exit(-1)

    working_dir      = _get_project_dir(args.project)
    src_path         = os.path.join(working_dir, config[kind]['lib_path'], args.module)
    module_repo_path = config[args.module]['clone']
    cfg              = config[kind]

    repo = git.Repo(module_repo_path)
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):
        print('Failed to checkin module {}. module repo is dirty:\n{}'.format(module, module_repo_path))
        print(repo.git.status())
        return

    dst = src_path.replace(os.path.expanduser('~'), '~', 1)
    try:
        repo.heads[project].checkout()
    except IndexError:
        print("ERROR: Branch '{}' doesn't exist in library for module '{}'. Have you run `librarian checkout {} {}`?".format(project, module, project, module))
        sys.exit(-1)

    print('Copying module "{}" from {}'.format(module, dst))

    include_re,exclude_re,should_include = _build_should_include(cfg)

    root_marker = cfg['root_marker']
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

    try:
        # Copy all files since project should only have included files unless
        # we manually copied them (in which case we'd want them copied back).
        _copy_and_overwrite(src_path, dst_path, _include_all)
    except FileNotFoundError:
        # TODO: Need clearer error here. How can I correct this if I cloned my project? Just run librarian anyway?
        print("ERROR: Module '{1}' cannot be found in project '{0}'. Have you run `librarian checkout {0} {1}`?".format(project, module))
        sys.exit(-1)
    finally:
        if restore_git:
            restore_git()

    single = cfg['rename_root_marker_pattern']
    if single:
        file = config[module].get('renamed_root_marker', '')
        if file:
            _rename_if_single_file(dst_path, file, re.compile(cfg['root_marker']))

    # TODO: nothing has changed, but these all return true.
    # print(repo.is_dirty(index=True))
    # print(repo.is_dirty(working_tree=True))
    # print(repo.is_dirty(untracked_files=True))
    # print(repo.is_dirty(submodules=True))
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True, submodules=True):

        # We deleted everything above. Restore any deleted files that
        # weren't copied to the project.
        for i in repo.index.diff(None):
            if i.deleted_file and not should_include('', i.a_path):
                repo.git.checkout('--', i.a_path)

        project_repo = git.Repo(working_dir)
        repo.git.add(A=True)
        msg = '''Librarian: Update with {0}'s latest

\t{0}@{1}
\tMessage:\n{2}'''.format(project, project_repo.head.commit.hexsha, project_repo.head.commit.message.strip())
        repo.index.commit(msg)
        print('Commit complete:\n'+ msg)
    else:
        print('No changes to apply')



def _get_project_dir(project):
    """Get the current project's directory.

    It's just the current working directory, but we do some validation to
    ensure you're not running from the wrong location.

    _get_project_dir() -> str
    """
    working_dir = os.getcwd()
    if working_dir.find(project) < 0:
        print("Current path ({}) doesn't contain name of project '{}'.".format(working_dir, project))
        try:
            answer = input("Are you in the right place? ").lower()
        except EOFError:
            answer = None
        if not answer:
            print("n")
            print("(Failed to read stdin. Assuming no.)")
            answer = 'n'
        if answer[0] != 'y':
            sys.exit(-1)
    return working_dir


def main():
    os.makedirs(CLONES_PATH, exist_ok=True)
    config = _read_config()
    args = _get_args()
    if   args.action == 'config':
        _apply_config(args, config)

    elif args.action == 'list':
        _list_module(args, config)

    elif args.action == 'acquire':
        _acquire_module(args, config)

    elif args.action == 'pull':
        _pull_module(args, config)

    elif args.action == 'checkout':
        _checkout_module(args, config)

    elif args.action == 'checkin':
        _checkin_module(args, config)

    _write_config(config)


if __name__ == "__main__":
    main()
