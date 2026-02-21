import json
import pandas as pd

# 1. Load the JSON data
file_path = 'hee.txt' 
with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract tables into a dictionary
tables_list = data.get('r', {}).get('dbiAccessorRes', {}).get('tables', [])
tables = {t['id']: t.get('data_rows', []) for t in tables_list}

# 2. Build Lookup Maps (Name to ID)
subjects_map = {s['id']: s.get('name') for s in tables.get('subjects', []) if s.get('name')}
teachers_map = {t['id']: t.get('name') for t in tables.get('teachers', []) if t.get('name')}
classes_map  = {c['id']: c.get('name') for c in tables.get('classes', []) if c.get('name')}
rooms_map    = {r['id']: r.get('name') for r in tables.get('classrooms', []) if r.get('name')}

# 3. Robust Period Mapping (Match times by ID)
periods_map = {}
for p in tables.get('periods', []):
    start, end = p.get('starttime'), p.get('endtime')
    if start and end:
        # Some files use 'id', some use the 'period' number
        if p.get('id'): periods_map[str(p.get('id'))] = (start, end)
        if p.get('period'): periods_map[str(p.get('period'))] = (start, end)

# Day bitmask mapping
days_map = {
    "10000": "Monday", "01000": "Tuesday", "00100": "Wednesday",
    "00010": "Thursday", "00001": "Friday", "000001": "Saturday",
    "0000001": "Sunday", "11111": "Full Week"
}

# 4. Map Lessons (Link Subject + Professor + List of Groups)
lessons_data = {}
for l in tables.get('lessons', []):
    sub_name = subjects_map.get(l.get('subjectid'))
    profs = [teachers_map.get(tid) for tid in l.get('teacherids', []) if teachers_map.get(tid)]
    prof_name = ", ".join(profs) if profs else None
    class_ids = l.get('classids', [])
    
    if sub_name and class_ids and prof_name:
        lessons_data[l['id']] = {
            "subject": sub_name,
            "professor": prof_name,
            "class_ids": class_ids
        }

# 5. Build Timetable with Room extraction
final_list = []
seen_records = set() # STRICT duplicate prevention

for card in tables.get('cards', []):
    lesson_id = card.get('lessonid')
    day_code = str(card.get('days', card.get('day', '')))
    period_id = str(card.get('period', ''))
    
    # Extract and join rooms (incase a card has multiple rooms)
    c_ids = card.get('classroomids', [])
    rooms = [rooms_map.get(rid) for rid in c_ids if rooms_map.get(rid)]
    room_str = ", ".join(rooms) if rooms else None
    
    if lesson_id in lessons_data:
        lesson = lessons_data[lesson_id]
        time_info = periods_map.get(period_id)
        day_name = days_map.get(day_code)
        
        # ONLY add if we have valid Day, Time, and Room (No N/A allowed)
        if time_info and day_name and room_str:
            start_t, end_t = time_info
            
            for class_id in lesson['class_ids']:
                group_name = classes_map.get(class_id)
                if group_name:
                    # Fingerprint including room to prevent duplicates
                    fingerprint = (lesson['subject'], group_name, lesson['professor'], day_name, start_t, room_str)
                    
                    if fingerprint not in seen_records:
                        final_list.append({
                            "subject": lesson['subject'],
                            "group_name": group_name,
                            "professor": lesson['professor'],
                            "week_day": day_name,
                            "start_time": start_t,
                            "end_time": end_t,
                            "room": room_str
                        })
                        seen_records.add(fingerprint)

# 6. Save and Sort
df = pd.DataFrame(final_list)
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
df['week_day'] = pd.Categorical(df['week_day'], categories=day_order, ordered=True)
df = df.sort_values(by=['group_name', 'week_day', 'start_time'])

df.to_csv('timetable_with_rooms.csv', index=False)
print(f"Extraction complete: 0 N/A values found. {len(df)} rows saved.")