
import re
import sys
from collections import defaultdict

def parse_log(logfile):
    func_times = defaultdict(list)
    # Only match lines with execution time
    time_pattern = re.compile(r"Temps d'exécution ([\w\.]+): ([0-9.]+) s")
    with open(logfile, encoding='utf-8') as f:
        for line in f:
            m = time_pattern.search(line)
            if m:
                func = m.group(1)
                elapsed = float(m.group(2))
                func_times[func].append(elapsed)
    return func_times

def print_stats(func_times):
    print(f"{'Function':40} {'Calls':>8} {'Total(s)':>12} {'Avg(s)':>10} {'Max(s)':>10}")
    print("-"*80)
    for func, times in sorted(func_times.items(), key=lambda x: -sum(x[1])):
        total = sum(times)
        avg = total / len(times)
        max_t = max(times)
        print(f"{func:40} {len(times):8d} {total:12.4f} {avg:10.6f} {max_t:10.6f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_log_times.py <logfile>")
        sys.exit(1)
    logfile = sys.argv[1]
    func_times = parse_log(logfile)
    print_stats(func_times)