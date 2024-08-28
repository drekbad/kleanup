#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime, timedelta
from shutil import disk_usage
from collections import defaultdict

# Editable priority directories
PRIORITY_DIRECTORIES = [
    '/root/.msf4/loot/',
    '/root/',
    '/home/kali/',
    '/mnt/'
]

# Directories to focus on after the priority list
TARGET_DIRECTORIES = ['/home', '/root', '/tmp', '/etc']

# Directories to always exclude
EXCLUDED_DIRECTORIES = [
    '/root/.local/',
    '/root/.cache/',
    '/root/.config/',
    '/home/kali/.local/',
    '/home/kali/.cache/',
    '/home/kali/.config/',
    '/root/.config/google-chrome/',
    '/root/.cache/google-chrome/',
    '/home/kali/.config/google-chrome/',
    '/home/kali/.cache/google-chrome/',
    '/root/.config/firefox/',
    '/root/.cache/firefox/',
    '/home/kali/.config/firefox/',
    '/home/kali/.cache/firefox/',
    '/root/.mozilla/firefox/',
    '/home/kali/.mozilla/firefox/'
]

# Function to format file sizes nicely
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0

# Function to get file time (created or modified) based on user choice
def get_file_time(path, use_modified=False):
    try:
        if use_modified:
            return datetime.fromtimestamp(os.path.getmtime(path))
        else:
            return datetime.fromtimestamp(os.stat(path).st_ctime)
    except FileNotFoundError:
        return None

# Function to check if a path should be excluded
def is_excluded_path(path):
    return any(path.startswith(excluded_dir) for excluded_dir in EXCLUDED_DIRECTORIES)

# Summarize directories with similar paths
def summarize_directories(dir_info):
    summarized_info = defaultdict(lambda: {'count': 0, 'size': 0, 'dir_count': 0, 'file_count': 0})
    for path, info in dir_info.items():
        common_path = "/".join(path.split("/")[:-2])  # Group by common higher-level path
        summarized_info[common_path]['count'] += info['count']
        summarized_info[common_path]['size'] += info['size']
        summarized_info[common_path]['dir_count'] += info['dir_count']
        summarized_info[common_path]['file_count'] += info['file_count']
    return summarized_info

# Function to calculate directory sizes and count files, skipping symbolic links and focusing on specific directories
def get_directory_info(start_date, end_date=None, use_modified=False, base_paths=None):
    dir_info = {}
    for base_path in base_paths:
        for root, dirs, files in os.walk(base_path, followlinks=False):
            # Skip excluded directories
            if is_excluded_path(root):
                continue

            count = 0
            total_size = 0
            dir_count = 0
            for file in files:
                filepath = os.path.join(root, file)
                if is_excluded_path(filepath) or os.path.islink(filepath):
                    continue
                try:
                    file_time = get_file_time(filepath, use_modified)
                    if file_time:
                        if end_date:
                            if start_date <= file_time < end_date:
                                count += 1
                                total_size += os.path.getsize(filepath)
                        else:
                            if file_time >= start_date:
                                count += 1
                                total_size += os.path.getsize(filepath)
                except (FileNotFoundError, PermissionError):
                    continue  # Skip files that can't be accessed
            # Skip directories that contain no files and whose subdirectories also contain no files
            if count > 0 or total_size > 0:
                dir_info[root] = {
                    'count': count,
                    'size': total_size,
                    'dir_count': len(dirs),
                    'file_count': count
                }
            elif dirs:  # Check if the subdirectories contain files
                subdir_total = 0
                for subdir in dirs:
                    subdir_path = os.path.join(root, subdir)
                    for subroot, subdirs, subfiles in os.walk(subdir_path, followlinks=False):
                        for subfile in subfiles:
                            subfile_path = os.path.join(subroot, subfile)
                            if not is_excluded_path(subfile_path):
                                try:
                                    subdir_total += os.path.getsize(subfile_path)
                                except (FileNotFoundError, PermissionError):
                                    continue  # Skip files that can't be accessed
                    if subdir_total > 0:
                        dir_info[root] = {
                            'count': count,
                            'size': subdir_total,
                            'dir_count': len(dirs),
                            'file_count': count
                        }
                        break
    return summarize_directories(dir_info)

# Function to list directory information with numbering and summaries
def list_directory_info(dir_info, header, start_number=1):
    print(f"\n{header}\n" + "-"*80)
    numbered_dirs = []
    display_count = start_number
    for dir_path, info in sorted(dir_info.items()):
        if dir_path and info['file_count'] > 0:  # Ensure path is not blank and has files
            print(f"{display_count}.\t({info['count']})\t{dir_path.ljust(40)}\t{format_size(info['size'])}")
            if info['dir_count'] > 15:
                print(f"\t  ({info['dir_count']} dirs)\t{format_size(info['size'])}")
            numbered_dirs.append(dir_path)
            display_count += 1
    return numbered_dirs

# Function to list files in the selected directories
def list_files_in_dir(dir_info, output_file):
    with open(output_file, 'a') as f:
        for dir_path, info in dir_info.items():
            for root, _, files in os.walk(dir_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    if is_excluded_path(filepath) or os.path.islink(filepath):
                        continue
                    try:
                        file_size = os.path.getsize(filepath)
                        created_time = get_file_time(filepath).strftime("%Y-%m-%d %H:%M:%S")
                        modified_time = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"{filepath},{format_size(file_size)},{created_time},{modified_time}\n")
                    except (FileNotFoundError, PermissionError):
                        continue  # Skip files that can't be accessed

# Function to calculate free space on disk
def check_disk_space(required_space):
    total, used, free = disk_usage('/')
    return free >= required_space, free

# Handle graceful shutdown on Ctrl+C
def signal_handler(sig, frame):
    print("\nShutdown requested... exiting gracefully.")
    sys.exit(0)

import signal
signal.signal(signal.SIGINT, signal_handler)

# Main script function
def main():
    use_modified = '--modified-on' in sys.argv
    start_date_input = input("Please provide the start date of activity (mm/dd/yy): ")
    try:
        start_date = datetime.strptime(start_date_input, "%m/%d/%y")
    except ValueError:
        print("Invalid date format. Please use mm/dd/yy.")
        return

    prior_date = start_date - timedelta(days=30)

    # Handle priority directories first
    print(f"Scanning priority directories for files {'modified' if use_modified else 'created'} since the specified date...")
    priority_files = get_directory_info(start_date, use_modified=use_modified, base_paths=PRIORITY_DIRECTORIES)
    new_dirs = list_directory_info(priority_files, "Priority Directories:", 1)

    final_dirs = []
    non_priority_files = {}  # Initialize to avoid reference errors

    # Prompt for selection or ignoring
    action = input("\nDo you want to (S)elect or (I)gnore directories from the priority list? ")
    if action.lower() not in ['s', 'i']:
        print("Invalid option. Please enter 'S' to select or 'I' to ignore.")
        return

    prompt_message = "\nPlease enter the numbers of directories to " + ("select" if action.lower() == 's' else "ignore") + " (comma or space separated, type ALL for all, or NONE to skip): "
    selected_dirs = input(prompt_message).split()

    if 'none' in [s.lower() for s in selected_dirs]:
        selected_dirs = []
    elif 'all' in [s.lower() for s in selected_dirs]:
        selected_dirs = list(range(1, len(new_dirs) + 1))
    else:
        selected_dirs = [int(i) for i in selected_dirs if i.isdigit()]

    if action.lower() == 's':
        final_dirs = [new_dirs[i-1] for i in selected_dirs]
    else:
        # Ignore the directories and their subdirectories
        final_dirs = [new_dirs[i-1] for i in range(1, len(new_dirs) + 1) if i not in selected_dirs]

    # Prompt whether to continue to non-priority directories
    proceed = input("\nDo you want to search non-priority directories as well? (y/n): ")
    if proceed.lower() == 'y':
        print(f"Scanning additional directories for files {'modified' if use_modified else 'created'} since the specified date...")
        non_priority_files = get_directory_info(start_date, use_modified=use_modified, base_paths=TARGET_DIRECTORIES)
        additional_dirs = list_directory_info(non_priority_files, "Additional Directories:", len(final_dirs) + 1)

        action = input("\nDo you want to (S)elect or (I)gnore directories from the additional list? ")
        if action.lower() not in ['s', 'i']:
            print("Invalid option. Please enter 'S' to select or 'I' to ignore.")
            return

        prompt_message = "\nPlease enter the numbers of directories to " + ("select" if action.lower() == 's' else "ignore") + " (comma or space separated, type ALL for all, or NONE to skip): "
        selected_dirs = input(prompt_message).split()

        if 'none' in [s.lower() for s in selected_dirs]:
            selected_dirs = []
        elif 'all' in [s.lower() for s in selected_dirs]:
            selected_dirs = list(range(1, len(additional_dirs) + 1))
        else:
            selected_dirs = [int(i) for i in selected_dirs if i.isdigit()]

        if action.lower() == 's':
            final_dirs.extend([additional_dirs[i-1] for i in selected_dirs])
        else:
            final_dirs.extend([additional_dirs[i-1] for i in range(1, len(additional_dirs) + 1) if i not in selected_dirs])

    # Calculate total size of selected directories
    total_size = sum(priority_files[dir_path]['size'] for dir_path in final_dirs if dir_path in priority_files) + \
                 sum(non_priority_files[dir_path]['size'] for dir_path in final_dirs if dir_path in non_priority_files)

    # Display total size before proceeding
    print(f"\nThe total size of files to be archived is \033[1m{format_size(total_size)}\033[0m")

    # Ensure user confirmation before archiving
    confirm = input("\nDo you want to proceed with archiving the selected directories? (y/n): ")
    if confirm.lower() != 'y':
        print("Archiving canceled by user.")
        return

    # Check disk space
    has_space, free_space = check_disk_space(total_size)
    if not has_space:
        print(f"Not enough disk space. Required: {format_size(total_size)}, Available: {format_size(free_space)}")
        return

    if total_size > free_space * 0.25:
        confirm = input(f"Warning: Archiving will consume more than 25% of free space ({format_size(total_size)}). Proceed? (y/n): ")
        if confirm.lower() != 'y':
            return

    # Get password and archive
    password = input("Please enter a password for the archive: ")

    # Prepare the list of directories with ARCHIVE/ prefix and full paths preserved
    archive_entries = []
    with open("filelist.txt", "w") as file_list:
        for dir_path in final_dirs:
            for root, _, files in os.walk(dir_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    if not is_excluded_path(filepath):
                        relative_path = os.path.relpath(filepath, "/")
                        archive_path = f"ARCHIVE/{relative_path}"
                        file_list.write(f"{filepath}\n")

    # Create the 7z archive with the directory structure preserved under ARCHIVE/ using file list
    archive_name = "archive.7z"
    command = ["7z", "a", "-p" + password, "-mhe=on", archive_name, "@filelist.txt"]
    result = subprocess.run(command, capture_output=True, text=True)

    # Check if the archiving process encountered any errors
    if result.returncode == 0:
        print("Archiving completed successfully.")
    else:
        print("Archiving failed with errors:")
        print(result.stderr)

    # Clean up temporary file list
    os.remove("filelist.txt")

    # Optionally output to file with detailed info
    if len(sys.argv) > 1 and sys.argv[1] == "-o":
        output_file = sys.argv[2]
        with open(output_file, 'w') as f:
            f.write(f"Directories containing files {'modified' if use_modified else 'created'} since {start_date_input}:\n" + "-"*80 + "\n")
            for dir_path, info in priority_files.items():
                f.write(f"({info['count']})\t{dir_path}\t{format_size(info['size'])}\n")
            f.write(f"\nDirectories containing files {'modified' if use_modified else 'created'} within 1 mo. prior to {start_date_input}:\n" + "-"*80 + "\n")
            for dir_path, info in non_priority_files.items():
                f.write(f"({info['count']})\t{dir_path}\t{format_size(info['size'])}\n")
        list_files_in_dir({dir_path: priority_files[dir_path] for dir_path in final_dirs if dir_path in priority_files}, output_file)
        list_files_in_dir({dir_path: non_priority_files[dir_path] for dir_path in final_dirs if dir_path in non_priority_files}, output_file)

if __name__ == "__main__":
    main()
