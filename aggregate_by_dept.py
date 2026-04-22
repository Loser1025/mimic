import csv
from collections import Counter, defaultdict

file_path = 'resignations.csv'
# dept_reasons[dept][reason] = count
dept_reasons = defaultdict(Counter)

try:
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        for row in reader:
            if len(row) > 11:
                dept = row[2].strip() if len(row) > 2 else "Unknown"
                reason_cell = row[11].strip()
                
                if not dept:
                    dept = "Unknown"
                
                if reason_cell:
                    # Split by comma in case there are multiple reasons
                    parts = [p.strip() for p in reason_cell.split(',')]
                    for p in parts:
                        # Normalize "待遇" and "待遇（給与）"
                        if "待遇" in p:
                            p = "待遇"
                        dept_reasons[dept][p] += 1

    # Print results for each department
    for dept, counts in dept_reasons.items():
        total = sum(counts.values())
        print(f"\n【事業部: {dept}】 (総理由件数: {total})")
        print("-" * 40)
        # Sort by frequency descending
        for reason, count in counts.most_common():
            percentage = (count / total) * 100 if total > 0 else 0
            print(f"{reason}: {count} ({percentage:.2f}%)")

except Exception as e:
    print(f"Error: {e}")
