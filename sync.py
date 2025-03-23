#import os
import time
import argparse
import logging
from pathlib import Path
from filecmp import dircmp

class Synchronizer():
    def __init__(self, source, dest, logfile, interval=600, follow_symlinks=True, dryrun=True, by_content=False):
		source_path = Path(source).absolute()
		if not (source_path.exists() and source_path.is_dir()):
			# source path does not exist
			# FAIL
		dest_path = Path(dest).absolute()
		if not (dest_path.exists() and dest_path.is_dir()):
			# dest path does not exist
			# FAIL
		if source_path.is_relative_to(dest_path) or dest_path.is_relative_to(source_path):
			# source or dest is relative to the other
			# FAIL
		log_path = Path(logfile).absolute()
		if not (log_path.parent.exists() and log_path.parent.is_dir()):
			# dir to create log file does not exist
			# FAIL
		self.next_run = time.time()
		self.source = source_path
        self.dest = dest_path
        self.follow_symlinks = follow_symlinks
        self.dryrun = dryrun
		self.by_content = by_content
        self.interval = interval
		self.logger = logging.getLogger(__name__)
		self.logger.addHandler(logging.FileHandler(log_path))
		self.logger.addHandler(logging.StreamHandler(sys.stdout))
	
	def compare_dirs(source, dest, shallow)
		comparison = dircmp(source, dest, shallow)
		self.copy_list += [source.joinpath(dir) for dir in comparison.left_only]
	
    def run(self):
		while True:
			dir_compared = dircmp(self.source_path, self.dest_path, not self.by_content)
			copy_list = dir_compared.left_only
			overwrite_files = dir_compared.diff_files + dir_compared.funny_files
			delete = dir_compared.right_only
			for subdir_name, subdir_compared in dir_compared.subdirs.items():
				
			# sync
			# wait
			self.next_run += self.interval
			logger.info("Sleeping intil next run")
			time.sleep(max(self.next_run - time.time(),0))


def main()
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