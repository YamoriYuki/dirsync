import os
import sys
import time
import shutil
import logging
import argparse
from pathlib import Path
from filecmp import dircmp

class Synchronizer():
    def __init__(self, source, dest, logfile, interval=600, follow_symlinks=True, dryrun=True, by_content=False):
        log_path = Path(logfile).absolute()
        if not (log_path.parent.exists() and log_path.parent.is_dir()):
            raise Exception("Invalid log file path")
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(logging.FileHandler(log_path))
        self.logger.addHandler(logging.StreamHandler(sys.stdout))
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("Synchonizer starting with params:")
        self.logger.debug(f"source = {source}")
        self.logger.debug(f"dest = {dest}")
        self.logger.debug(f"logfile = {logfile}")
        self.logger.debug(f"interval = {interval}")
        self.logger.debug(f"follow_symlinks = {follow_symlinks}")
        self.logger.debug(f"dryrun = {dryrun}")
        self.logger.debug(f"by_content = {by_content}")
        source_path = Path(source).absolute()
        if not follow_symlinks:
            for parent in source_path.parents:
                if parent.is_symlink:
                    self.logger.critical(f"SOURCE path {source_path} contains symlink(s) but --do-not-follow-symlinks is enabled")
                    raise Exception(f"SOURCE path contains symlink(s)")
        if not source_path.exists():
            self.logger.critical(f"SOURCE path {source_path} does not exist")
            raise Exception(f"SOURCE path does not exist")
        if not source_path.is_dir():
            self.logger.critical(f"SOURCE path {source_path} is not a directory")
            raise Exception(f"SOURCE path is not a directory")
        source_path_resolved = source_path.resolve()
        if source_path_resolved != source_path:
            source_path = source_path_resolved
            self.logger.info(f"SOURCE path {source} resolved to {source_path}")
        dest_path = Path(dest).absolute()
        if not follow_symlinks:
            for parent in dest_path.parents:
                if parent.is_symlink:
                    self.logger.critical(f"DEST path {dest_path} contains symlink(s) but --do-not-follow-symlinks is enabled")
                    raise Exception(f"DEST path contains symlink(s)")
        if not dest_path.exists():
            self.logger.critical(f"DEST path {dest_path} does not exist")
            raise Exception(f"DEST path does not exist")
        if not dest_path.is_dir():
            self.logger.critical(f"DEST path {dest_path} is not a directory")
            raise Exception(f"DEST path is not a directory")
        dest_path_resolved = dest_path.resolve()
        if dest_path_resolved != dest_path:
            dest_path = dest_path_resolved
            self.logger.info(f"DEST path {dest} resolved to {dest_path}")
        if source_path.is_relative_to(dest_path) or dest_path.is_relative_to(source_path):
            self.logger.critical(f"SOURCE {source_path} or DEST {dest_path} is relative to the other.")
            raise Exception(f"SOURCE or DEST is relative to the other.")
        self.next_run = time.time()
        self.source = source_path
        self.dest = dest_path
        self.follow_symlinks = follow_symlinks
        self.dryrun = dryrun
        self.by_content = by_content
        self.interval = interval
        self.ignore_list = []
        self.seen_inos = {}
    
    def sync_dirs(self, source, dest, compared):
        items_to_check = [source.joinpath(item) for item in compared.left_list] + [dest.joinpath(item) for item in compared.right_list]
        funny_items = [item for item in items_to_check if self.is_funny(item, self.follow_symlinks)]
        self.ignore_list += funny_items
        for item in funny_items:
            self.logger.warning(f"{item} in not a regular file, symlink or directory. Ignoring.")
        for dir_name, dir_compared in [ (dir, cmp) for (dir, cmp) in compared.subdirs.items() if not source.joinpath(dir) in self.ignore_list]:
            dir_path = source.joinpath(dir_name)
            ino = os.stat(dir_path).st_ino
            if ino in self.seen_inos.keys():
                self.logger.warning(f"Directory {dir_path} has been previously encountered at {self.seen_inos[ino]}, skipping.")
            else:
                self.seen_inos[ino] = dir_path
                self.sync_dirs(source.joinpath(dir_name), dest.joinpath(dir_name), dir_compared)
        for item in [ dest.joinpath(item) for item in compared.right_only if not dest.joinpath(item) in self.ignore_list]:
            if not self.follow_symlinks and item.is_symlink():
                self.logger.info(f"Deleting symlink {item}.")
                item.unlink()
            elif item.is_dir():
                self.logger.info(f"Deleting directory tree {item}.")
                shutil.rmtree(item)
            elif item.is_file():
                self.logger.info(f"Deleting file {item}.")
                item.unlink()
            else:
                self.logger.error(f"SHOULD NOT HAPPEN: {item} is not a regular file, symlink or directory. NOT deleting")

        for item in [ item for item in compared.left_only if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            if not self.follow_symlinks and source_path.is_symlink():
                self.logger.info(f"Copying symlink {source_path}.")
                self.copy_symlink(source_path, dest_path)
            elif source_path.is_dir():
                self.logger.info(f"Copying directory tree {source_path}.")
                shutil.copytree(source_path, dest_path, not self.follow_symlinks)
            elif source_path.is_file():
                self.logger.info(f"Copying file {source_path}.")
                shutil.copy2(source_path, dest_path)
            else:
                self.logger.error(f"SHOULD NOT HAPPEN: {source_path} is not a regular file, symlink or directory. NOT copying")

        for item in [ item for item in compared.common_funny if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            if dest_path in self.ignore_list:
                self.logger.warn(f"Cannot replace ingnored {dest_path} with {source_path}")
                continue
            if not self.follow_symlinks and source_path.is_symlink():
                self.logger.info(f"Replacing {dest_path} with symlink {source_path}.")
                if dest_path.is_dir():
                    shutil.rmtree(dest_path)
                else:
                    dest_path.unlink()
                self.copy_symlink(source_path, dest_path)
            elif source_path.is_dir():
                self.logger.info(f"Replacing {dest_path} with directory tree {source_path}.")
                if dest_path.is_dir():
                    shutil.rmtree(dest_path)
                else:
                    dest_path.unlink()
                shutil.copytree(source_path, dest_path, not self.follow_symlinks)
            elif source_path.is_file():
                self.logger.info(f"Replacing {dest_path} with file {source_path}.")
                if dest_path.is_dir():
                    shutil.rmtree(dest_path)
                else:
                    dest_path.unlink()
                shutil.copy2(source_path, dest_path)
            else:
                self.logger.error(f"SHOULD NOT HAPPEN: {source_path} is not a regular file, symlink or directory. NOT copying")

        for item in [ item for item in compared.diff_files if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            if dest_path in self.ignore_list:
                self.logger.warn(f"Cannot replace ingnored {dest_path} with {source_path}")
                continue
            if not self.follow_symlinks and source_path.is_symlink():
                self.logger.info(f"Replacing {dest_path} with symlink {source_path}.")
                dest_path.unlink()
                self.copy_symlink(source_path, dest_path)
            elif source_path.is_file():
                self.logger.info(f"Replacing {dest_path} with file {source_path}.")
                dest_path.unlink()
                shutil.copy2(source_path, dest_path)
            else:
                self.logger.error(f"SHOULD NOT HAPPEN: {source_path} is not a regular file or symlink. NOT copying")

    def copy_symlink(self, source, dest):
        link_dest = Path(source.readlink())
        if link_dest.is_absolute() and link_dest.is_relative_to(self.source):
            link_target_in_dest = self.dest.joinpath(link_dest.relative_to(self.source))
            dest.symlink_to(link_target_in_dest, link_dest.is_dir())
        else:
            shutil.copy2(source, dest, follow_symlinks=False)
    
    def run(self):
        while True:
            self.logger.info("Starting sync")
            self.sync_dirs(self.source, self.dest, dircmp(self.source, self.dest, shallow = not self.by_content))
            self.seen_inos.clear()
            self.next_run += self.interval
            self.logger.info("Sync complete, sleeping until next run")
            time.sleep(max(self.next_run - time.time(),0))
    
    @staticmethod
    def is_funny(path, follow_symlinks):
        return not (path.is_dir(follow_symlinks = follow_symlinks) or
                    path.is_file(follow_symlinks = follow_symlinks) or
                    path.is_symlink())


def main():
    arg_parser = argparse.ArgumentParser(
                    prog='Synchornizer',
                    description='Periodically synchornizes files and folders from SOURCE to DESTINATION',
                    epilog='',
                    exit_on_error=False)
    arg_parser.add_argument('source', metavar='SOURCE')
    arg_parser.add_argument('dest', metavar='DESTINATION')
    arg_parser.add_argument('--interval', default=600, type=int)
    arg_parser.add_argument('--log-file', required=True)
    arg_parser.add_argument('--do-not-follow-symlinks', action='store_true')
    arg_parser.add_argument('--dry-run', action='store_true')
    arg_parser.add_argument('--by-content', action='store_true')
    args = arg_parser.parse_args()

    s = Synchronizer(args.source, args.dest, args.log_file, args.interval, not args.do_not_follow_symlinks, args.dry_run)
    s.run()

if __name__ == '__main__':
    main()