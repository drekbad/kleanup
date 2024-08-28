#!/usr/bin/env python3

import os
import sys
import subprocess
from datetime import datetime, timedelta
from shutil import disk_usage

# Directories to focus on
TARGET_DIRECTORIES = ['/home', '/root', '/tmp', '/etc']

# Function to format file sizes nicely
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0

# Function to get file creation time (works on Linux with ext4 filesystems)
def get_creation_time(path):
    try:
        return datetime.fromtimestamp(os.stat(path).st_ctime)
    except FileNotFoundError:
        return None

# Function to calculate directory sizes and count files, skipping symbolic links and focusing on specific directories
def get_directory_info(start_date, end_date=None):
    dir_info = {}
    for base_path in TARGET_DIRECTORIES:
        for root, dirs, files in os.walk(base_path, followlinks=False):
            count = 0
            total_size = 0
            for file in files:
                filepath = os.path.join(root, file)
                if os.path.islink(filepath):
                    continue
                creation_time = get_creation_time(filepath)
                if creation_time:
                    if end_date:
                        if start_date <= creation_time < end_date:
                            count += 1
                            total_size += os.path.getsize(filepath)
                    else:
                        if creation_time >= start_date:
                            count += 1
                            total_size += os.path.getsize(filepath)
            # Exclude directories with total size less than 0.1B
            if count > 0 and total_size >= 0.1:
                dir_info[root] = {'count': count, 'size': total_size}
    return dir_info

# Function to list directory information with numbering
def list_directory_info(dir_info, header, start_number=1):
    print(f"\n{header}\n" + "-"*80)
    numbered_dirs = []
    for idx, (dir_path, info) in enumerate(dir_info.items(), start_number):
        print(f"{idx}.\t({info['count']})\t{dir_path.ljust(40)}\t{format_size(info['size'])}")
        numbered_dirs.append(dir_path)
    return numbered_dirs

# Function to list files in the selected directories
def list_files_in_dir(dir_info, output_file):
    with open(output_file, 'a') as f:
        for dir_path, info in dir_info.items():
            for root, _, files in os.walk(dir_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    if os.path.islink(filepath):
                        continue
                    file_size = os.path.getsize(filepath)
                    created_time = get_creation_time(filepath).strftime("%Y-%m-%d %H:%M:%S")
                    modified_time = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{filepath},{format_size(file_size)},{created_time},{modified_time}\n")

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
    start_date_input = input("Please provide the start date of activity (mm/dd/yy): ")
    try:
        start_date = datetime.strptime(start_date_input, "%m/%d/%y")
    except ValueError:
        print("Invalid date format. Please use mm/dd/yy.")
        return

    prior_date = start_date - timedelta(days=30)

    # Find directories with files created since start_date
    print("Scanning filesystem for files created since the specified date...")
    new_files = get_directory_info(start_date)
    prior_files = get_directory_info(prior_date, start_date)

    # Display directory info to user
    new_dirs = list_directory_info(new_files, f"Directories containing files created since {start_date_input}:", 1)
    prior_dirs = list_directory_info(prior_files, f"Directories containing files created within 1 mo. prior to {start_date_input}:", len(new_dirs) + 1)

    # Prompt for selection or ignoring
    action = input("\nDo you want to (S)elect or (I)gnore directories? ")
    if action.lower() not in ['s', 'i']:
        print("Invalid option. Please enter 'S' to select or 'I' to ignore.")
        return

    prompt_message = "\nPlease enter the numbers of directories to " + ("select" if action.lower() == 's' else "ignore") + " (comma or space separated, type ALL for all in the first list, or BOTH for all from both lists): "
    selected_dirs = input(prompt_message).split()

    if 'both' in [s.lower() for s in selected_dirs]:
        selected_dirs = list(range(1, len(new_dirs) + len(prior_dirs) + 1))
    elif 'all' in [s.lower() for s in selected_dirs]:
        selected_dirs = list(range(1, len(new_dirs) + 1))
    else:
        selected_dirs = [int(i) for i in selected_dirs if i.isdigit()]

    # Determine final list of directories
    if action.lower() == 's':
        final_dirs = [new_dirs[i-1] for i in selected_dirs if i <= len(new_dirs)] + \
                     [prior_dirs[i-len(new_dirs)-1] for i in selected_dirs if i > len(new_dirs)]
    else:
        final_dirs = [new_dirs[i-1] for i in range(1, len(new_dirs) + 1) if i not in selected_dirs] + \
                     [prior_dirs[i-len(new_dirs)-1] for i in range(len(new_dirs) + 1, len(new_dirs) + len(prior_dirs) + 1) if i not in selected_dirs]

    # Calculate total size of selected directories
    total_size = sum(new_files[dir_path]['size'] for dir_path in final_dirs if dir_path in new_files) + \
                 sum(prior_files[dir_path]['size'] for dir_path in final_dirs if dir_path in prior_files)

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
    print(f"Password entered: {password}")

    # Create the 7z archive
    archive_name = "archive.7z"
    command = ["7z", "a", "-p" + password, "-mhe=on", archive_name] + final_dirs
    subprocess.run(command)

    # Optionally output to file with detailed info
    if len(sys.argv) > 1 and sys.argv[1] == "-o":
        output_file = sys.argv[2]
        with open(output_file, 'w') as f:
            f.write(f"Directories containing files created since {start_date_input}:\n" + "-"*80 + "\n")
            for dir_path, info in new_files.items():
                f.write(f"({info['count']})\t{dir_path}\t{format_size(info['size'])}\n")
            f.write(f"\nDirectories containing files created within 1 mo. prior to {start_date_input}:\n" + "-"*80 + "\n")
            for dir_path, info in prior_files.items():
                f.write(f"({info['count']})\t{dir_path}\t{format_size(info['size'])}\n")
        list_files_in_dir({dir_path: new_files[dir_path] for dir_path in final_dirs if dir_path in new_files}, output_file)
        list_files_in_dir({dir_path: prior_files[dir_path] for dir_path in final_dirs if dir_path in prior_files}, output_file)

    print("Archiving completed successfully.")

if __name__ == "__main__":
    main()
