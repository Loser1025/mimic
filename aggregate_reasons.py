import csv
from collections import Counter

file_path = 'resignations.csv'
reasons = []

try:
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header
        
        for row in reader:
            if len(row) > 11:
                reason_cell = row[11].strip()
                if reason_cell:
                    # Split by comma in case there are multiple reasons
                    parts = [p.strip() for p in reason_cell.split(',')]
                    reasons.extend(parts)

    counts = Counter(reasons)
    total = sum(counts.values())
    
    print(f"Total mentions: {total}")
    print("-" * 30)
    # Sort by frequency descending
    for reason, count in counts.most_common():
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"{reason}: {count} ({percentage:.2f}%)")

except Exception as e:
    print(f"Error: {e}")
