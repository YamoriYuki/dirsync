import os
import sys
import time
import shutil
import logging
import argparse
from pathlib import Path
from filecmp import dircmp

class Synchronizer():
    def __init__(self, source, dest, logfile, interval=600, follow_symlinks=True, dryrun=True, by_content=False, stop_on_errors=False, one_shot=False):
        log_path = Path(logfile).absolute()
        if not (log_path.parent.exists() and log_path.parent.is_dir()):
            raise Exception("Invalid log file path")
        self.logger = logging.getLogger(__name__)
        log_formatter = logging.Formatter('%(asctime)s - %(module)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(log_formatter)
        self.logger.addHandler(file_handler)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(log_formatter)
        self.logger.addHandler(stdout_handler)
        #self.logger.setLevel(logging.DEBUG)
        self.logger.setLevel(logging.INFO)
        self.logger.debug("Synchonizer starting with params:")
        self.logger.debug(f"source = {source}")
        self.logger.debug(f"dest = {dest}")
        self.logger.debug(f"logfile = {logfile}")
        self.logger.debug(f"interval = {interval}")
        self.logger.debug(f"follow_symlinks = {follow_symlinks}")
        self.logger.debug(f"dryrun = {dryrun}")
        self.logger.debug(f"by_content = {by_content}")
        self.logger.debug(f"stop_on_errors = {stop_on_errors}")
        self.logger.debug(f"one_shot = {one_shot}")
        # Following section may raise exceptions during path checks in the setup process.
        # Letting them propagate and stop execution is the desired result here.
        source_path = Path(source).absolute()
        if not follow_symlinks:
            for parent in source_path.parents:
                if parent.is_symlink():
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
                if parent.is_symlink():
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
        self.source_inos = {}
        for parent in source_path.parents:
            self.source_inos[parent.stat().st_ino] = parent
        self.source_inos[source_path.stat().st_ino] = source_path
        self.ignore_list = []
        self.seen_inos = {}
        self.source = source_path
        self.dest = dest_path
        self.follow_symlinks = follow_symlinks
        self.dryrun = dryrun
        self.by_content = by_content
        self.stop_on_errors = stop_on_errors
        self.one_shot = one_shot
        self.interval = interval
        self.next_run = time.time()

    def sync_dirs(self, source, dest, compared):
        items_to_check = [source.joinpath(item) for item in compared.left_list] + [dest.joinpath(item) for item in compared.right_list]
        funny_items = [item for item in items_to_check if self.is_funny(item, self.follow_symlinks)]
        self.ignore_list += funny_items
        for item in funny_items:
            self.logger.warning(f"{item} in not a regular file, symlink or directory. Ignoring.")
        for dir_name, dir_compared in [ (dir, cmp) for (dir, cmp) in compared.subdirs.items() if not source.joinpath(dir) in self.ignore_list]:
            dir_path = source.joinpath(dir_name)
            try:
                ino = dir_path.stat(follow_symlinks=self.follow_symlinks).st_ino
                if ino in self.seen_inos.keys():
                    self.logger.warning(f"Directory {dir_path} has been previously encountered at {self.seen_inos[ino]}, skipping.")
                else:
                    self.seen_inos[ino] = dir_path
                    self.sync_dirs(source.joinpath(dir_name), dest.joinpath(dir_name), dir_compared)
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered while processing '{dir_path}'. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered while processing '{dir_path}'. Continuing.")
        for item in [ dest.joinpath(item) for item in compared.right_only if not dest.joinpath(item) in self.ignore_list]:
            try:
                if self.dryrun:
                    self.logger.info(f"Dryrun enabled. NOT deleting {item}.")
                    continue
                if not self.follow_symlinks and item.is_symlink():
                    self.logger.info(f"Deleting symlink {item}.")
                    item.unlink()
                elif item.is_dir(follow_symlinks=self.follow_symlinks):
                    self.logger.info(f"Deleting directory tree {item}.")
                    shutil.rmtree(item)
                elif item.is_file():
                    self.logger.info(f"Deleting file {item}.")
                    item.unlink()
                else:
                    raise Exception(f"SHOULD NOT HAPPEN: {item} is not a regular file, symlink or directory. NOT deleting.")
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered while processing '{item}'. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered while processing '{item}'. Continuing.")
        for item in [ item for item in compared.left_only if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            try:
                if self.dryrun:
                    self.logger.info(f"Dryrun enabled. NOT copying {item}.")
                    continue
                if not self.follow_symlinks and source_path.is_symlink():
                    self.logger.info(f"Copying symlink {source_path}.")
                    self.copy_symlink(source_path, dest_path)
                elif source_path.is_dir(follow_symlinks=self.follow_symlinks):
                    self.logger.info(f"Copying directory tree {source_path}.")
                    if self.copy_tree(source_path, dest_path):
                        shutil.copytree(source_path, dest_path, not self.follow_symlinks)
                elif source_path.is_file(follow_symlinks=self.follow_symlinks):
                    self.logger.info(f"Copying file {source_path}.")
                    shutil.copy2(source_path, dest_path)
                else:
                    raise Exception(f"SHOULD NOT HAPPEN: {source_path} is not a regular file, symlink or directory. NOT copying")
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Continuing.")
        for item in [ item for item in compared.common_funny if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            try:
                if self.dryrun:
                    self.logger.info(f"Dryrun enabled. NOT replacing {dest_path} with {source_path}.")
                    continue
                if dest_path in self.ignore_list:
                    self.logger.warn(f"Cannot replace ingnored {dest_path} with {source_path}")
                    continue
                if source_path.is_dir(follow_symlinks=self.follow_symlinks):
                    self.logger.info(f"Replacing {dest_path} with directory tree {source_path}.")
                    if dest_path.is_dir(follow_symlinks=self.follow_symlinks):
                        shutil.rmtree(dest_path)
                    else:
                        dest_path.unlink()
                    if self.copy_tree(source_path, dest_path):
                        shutil.copytree(source_path, dest_path, not self.follow_symlinks)
                else:
                    self.copy_file(source_path, dest_path)
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Continuing.")
        for item in [ item for item in compared.diff_files if not source.joinpath(item) in self.ignore_list]:
            source_path = source.joinpath(item)
            dest_path = dest.joinpath(item)
            try:
                if self.dryrun:
                    self.logger.info(f"Dryrun enabled. NOT replacing {dest_path} with {source_path}.")
                    continue
                if dest_path in self.ignore_list:
                    self.logger.warn(f"Cannot replace ingnored {dest_path} with {source_path}")
                    continue
                self.copy_file(source_path, dest_path)
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered while processing '{source_path}'. Continuing.")

    def copy_tree(self, source, dest):
        if self.is_funny(source, self.follow_symlinks):
            self.logger.warning(f"{item} in not a regular file, symlink or directory. Ignoring.")
            return False
        ino = source.stat().st_ino
        if ino in self.seen_inos.keys():
            self.logger.warning(f"Directory {source} has been previously encountered at {self.seen_inos[ino]}, skipping.")
            return False
        else:
            self.seen_inos[ino] = source
        results = {item : self.copy_tree(item, dest.joinpath(item.name)) for item in source.iterdir() if item.is_dir(follow_symlinks=self.follow_symlinks)}
        if all(results.values()):
            return True
        else:
            for item, safe in results.items():
                if safe:
                    shutil.copytree(item, dest.joinpath(item.name), not self.follow_symlinks)
            for item in source.iterdir():
                if self.is_funny(item, self.follow_symlinks):
                    self.logger.warning(f"{item} in not a regular file, symlink or directory. Ignoring.")
                    continue
                if (not self.follow_symlinks and item.is_symlink()) or item.is_file(follow_symlinks=self.follow_symlinks):
                    dest.mkdir(parents=True)
                    self.copy_file(item, dest.joinpath(item.name))
            return False
            
    def copy_file(self, source, dest):
        if not self.follow_symlinks and source.is_symlink():
            if dest.exists():
                self.logger.info(f"Removing {dest}.")
                if dest.is_dir():
                    shutil.rmtree(dest, follow_symlinks=self.follow_symlinks)
                else:
                    dest.unlink()
            self.logger.info(f"Copying {source} to {dest}.")
            self.copy_symlink(source, dest)
        elif source.is_file():
            if dest.exists():
                self.logger.info(f"Removing {dest}.")
                if dest.is_dir():
                    shutil.rmtree(dest, follow_symlinks=self.follow_symlinks)
                else:
                    dest.unlink()
            self.logger.info(f"Copying {source} to {dest}.")
            shutil.copy2(source, dest)
        else:
            raise Exception(f"SHOULD NOT HAPPEN: {source} is not a regular file or symlink. NOT copying")

    def copy_symlink(self, source, dest):
        link_dest = source.readlink()
        if link_dest.drive.startswith('\\\\?\\'):
            link_dest = Path(str(link_dest).removeprefix('\\\\?\\'))
        if link_dest.is_absolute() and link_dest.is_relative_to(self.source):
            link_target_in_dest = self.dest.joinpath(link_dest.relative_to(self.source))
            dest.symlink_to(link_target_in_dest, link_dest.is_dir())
        else:
            shutil.copy2(source, dest, follow_symlinks=False)

    def run(self):
        while True:
            self.logger.info("Starting sync")
            self.seen_inos |= self.source_inos
            try:
                self.sync_dirs(self.source, self.dest, dircmp(self.source, self.dest, shallow = not self.by_content))
            except Exception as e:
                if self.stop_on_errors:
                    self.logger.error(f"Error '{e}' encountered. Exitting.")
                    sys.exit(1)
                else:
                    self.logger.error(f"Error '{e}' encountered. Continuing.")
            self.seen_inos.clear()
            if self.one_shot:
                break
            self.next_run += self.interval
            self.logger.info("Sync complete, sleeping until next run")
            time.sleep(max(self.next_run - time.time(),0))

    @staticmethod
    def is_funny(path, follow_symlinks):
        return path.is_junction() or not (path.is_dir(follow_symlinks = follow_symlinks) or
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
    arg_parser.add_argument('--stop-on-errors', action='store_true')
    arg_parser.add_argument('--one-shot', action='store_true')
    try:
        args = arg_parser.parse_args()
    except argparse.ArgumentError:
        arg_parser.print_help()
        sys.exit(1)

    s = Synchronizer(source = args.source,
                     dest = args.dest,
                     logfile = args.log_file,
                     interval = args.interval,
                     follow_symlinks = not args.do_not_follow_symlinks,
                     dryrun = args.dry_run,
                     by_content = args.by_content,
                     stop_on_errors = args.stop_on_errors,
                     one_shot = args.one_shot)
    s.run()

if __name__ == '__main__':
    main()