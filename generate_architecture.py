import os

"""
Script to generate a complete hierarchical view of the project architecture.
It writes the structure to 'architecture_projet.txt' at the root of the project.
"""

def write_tree(root_dir, output_file):
    try:
        this_file = os.path.basename(__file__)
    except NameError:
        this_file = None
    with open(output_file, 'w', encoding='utf-8') as f:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Ignore hidden files and folders
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            rel_path = os.path.relpath(dirpath, root_dir)
            indent_level = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
            indent = '    ' * indent_level
            if rel_path != '.':
                f.write(f"{indent}{os.path.basename(dirpath)}/\n")
            for filename in sorted(filenames):
                if filename.startswith('.') or (this_file and filename == this_file):
                    continue
                f.write(f"{indent}    {filename}\n")

if __name__ == "__main__":
    try:
        ROOT = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        # __file__ is not defined in interactive environments (e.g., DataSpell console)
        ROOT = os.getcwd()
    OUTPUT = os.path.join(ROOT, "architecture_projet.txt")
    write_tree(ROOT, OUTPUT)
    # Print only if running in a standard terminal, not in an IDE console
    try:
        import sys
        if hasattr(sys, 'ps1') or sys.flags.interactive:
            pass  # Likely in an interactive shell, do not print
        else:
            print(f"Project architecture written to {OUTPUT}")
    except Exception:
        pass
