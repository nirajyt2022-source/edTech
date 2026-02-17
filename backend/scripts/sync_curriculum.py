#!/usr/bin/env python3
"""
PRODUCTION-READY: Sync curriculum_canon.json from slot_engine.py

Ensures frontend dropdown only shows working topics.

FIXES INCLUDED:
1. ✅ Class 1/2 Science → EVS  
2. ✅ Correct logic_tags per subject (Science gets 'observation', not 'numerical')
3. ✅ All Maths topics extracted correctly
4. ✅ Only topics with working generation logic (has allowed_skill_tags)

USAGE:
  cd backend && python scripts/sync_curriculum.py
  
Then restart backend to reload curriculum.
"""
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
SLOT_ENGINE_PATH = BACKEND_DIR / "app" / "services" / "slot_engine.py"
CURRICULUM_PATH = BACKEND_DIR / "app" / "data" / "curriculum_canon.json"

# Subject mapping from skill tag prefix
SKILL_PREFIX_TO_SUBJECT = {
    # Check specific prefixes FIRST (order matters)
    'mth_c1_': 'Maths', 'mth_c2_': 'Maths', 'mth_c3_': 'Maths', 'mth_c4_': 'Maths', 'mth_c5_': 'Maths',
    'eng_c1_': 'English', 'eng_c2_': 'English', 'eng_c3_': 'English', 'eng_c4_': 'English', 'eng_c5_': 'English',
    'sci_c1_': 'EVS', 'sci_c2_': 'EVS', 'sci_c3_': 'Science', 'sci_c4_': 'Science', 'sci_c5_': 'Science',
    'hin_c1_': 'Hindi', 'hin_c2_': 'Hindi', 'hin_c3_': 'Hindi', 'hin_c4_': 'Hindi', 'hin_c5_': 'Hindi',
    'comp_c1_': 'Computer', 'comp_c2_': 'Computer', 'comp_c3_': 'Computer', 'comp_c4_': 'Computer', 'comp_c5_': 'Computer',
    'gk_c3_': 'GK', 'gk_c4_': 'GK', 'gk_c5_': 'GK',
    'moral_c1_': 'Moral Science', 'moral_c2_': 'Moral Science', 'moral_c3_': 'Moral Science', 
    'moral_c4_': 'Moral Science', 'moral_c5_': 'Moral Science',
    'health_c1_': 'Health', 'health_c2_': 'Health', 'health_c3_': 'Health', 'health_c4_': 'Health', 'health_c5_': 'Health',
    # Generic class prefixes (fallback - must come AFTER specific ones)
    'c1_': 'Maths', 'c2_': 'Maths', 'c3_': 'Maths', 'c4_': 'Maths', 'c5_': 'Maths',
}

# CRITICAL FIX: Correct logic_tags by subject
SUBJECT_LOGIC_TAGS = {
    'Maths': ['numerical', 'spatial', 'logical'],
    'English': ['vocabulary', 'reading_comprehension', 'grammar'],
    'EVS': ['observation', 'environment', 'life_science'],
    'Science': ['observation', 'experimentation', 'scientific_reasoning'],
    'Hindi': ['vocabulary', 'reading_comprehension', 'grammar'],
    'GK': ['factual_recall', 'current_awareness'],
    'Computer': ['procedural', 'technology'],
    'Health': ['observation', 'wellness'],
    'Moral Science': ['ethical_reasoning', 'social_awareness'],
}

def extract_topics_from_slot_engine():
    """Extract all topics from TOPIC_PROFILES with working generation logic."""
    with open(SLOT_ENGINE_PATH) as f:
        slot_engine = f.read()
    
    topics = []
    
    # Find all topic profile entries: "Topic Name": { ... "allowed_skill_tags": [...] ... }
    for match in re.finditer(r'"([^"]+)"\s*:\s*\{', slot_engine):
        topic_name = match.group(1)
        start_pos = match.end()
        snippet = slot_engine[start_pos:start_pos+2000]
        
        # CRITICAL: Only extract topics with allowed_skill_tags (= working generation)
        # This skips LEARNING_OBJECTIVES and TOPIC_CONTEXT_BANK entries
        if '"allowed_skill_tags"' not in snippet:
            continue
        
        # Extract grade from topic name if present: "Addition (Class 1)" → 1
        grade_match = re.search(r'\(Class (\d)\)', topic_name)
        if grade_match:
            grade = int(grade_match.group(1))
            # Remove (Class X) suffix for cleaner dropdown display
            clean_name = re.sub(r'\s*\(Class \d\)', '', topic_name).strip()
        else:
            # Infer grade from skill tags: "c1_add_basic" → Class 1
            skill_tags = re.findall(r'"([a-z0-9_]+)"', snippet[:500])
            grade = None
            
            if skill_tags:
                first_tag = skill_tags[0]
                # Pattern 1: c1_add_basic → Class 1
                match_c = re.match(r'c(\d)_', first_tag)
                if match_c:
                    grade = int(match_c.group(1))
                else:
                    # Pattern 2: mth_c3_add → Class 3
                    match_prefix = re.search(r'_c(\d)_', first_tag)
                    if match_prefix:
                        grade = int(match_prefix.group(1))
            
            # Skip topics without determinable grade
            if grade is None:
                continue
            
            clean_name = topic_name
        
        # Determine subject
        # STEP 1: Check explicit "subject" field in profile
        subj_match = re.search(r'"subject"\s*:\s*"([^"]+)"', snippet)
        if subj_match:
            subject = subj_match.group(1)
            # CRITICAL FIX: Class 1/2 Science → EVS
            if subject == "Science" and grade in [1, 2]:
                subject = "EVS"
        else:
            # STEP 2: Infer from skill tag prefix
            skill_tags = re.findall(r'"([a-z0-9_]+)"', snippet[:500])
            subject = None
            
            if skill_tags:
                first_tag = skill_tags[0]
                # Check prefixes in order (longest first to match sci_c1_ before c1_)
                for prefix in sorted(SKILL_PREFIX_TO_SUBJECT.keys(), key=len, reverse=True):
                    if first_tag.startswith(prefix):
                        subject = SKILL_PREFIX_TO_SUBJECT[prefix]
                        break
            
            # STEP 3: Fallback - guess from topic name keywords
            if subject is None:
                name_lower = topic_name.lower()
                if any(kw in name_lower for kw in ['add', 'subtract', 'multiply', 'divide', 'number', 'fraction', 'decimal', 'geometry', 'shape', 'measurement']):
                    subject = 'Maths'
                elif any(kw in name_lower for kw in ['noun', 'verb', 'sentence', 'grammar', 'reading', 'writing', 'comprehension', 'phonics', 'alphabet']):
                    subject = 'English'
                elif any(kw in name_lower for kw in ['plant', 'animal', 'ecosystem', 'digestive', 'water cycle', 'food', 'body', 'seasons']):
                    subject = 'EVS' if grade in [1, 2] else 'Science'
                elif any(kw in name_lower for kw in ['hindi', 'vyanjan', 'matra', 'varnamala', 'swar']):
                    subject = 'Hindi'
                elif any(kw in name_lower for kw in ['computer', 'mouse', 'keyboard', 'typing', 'desktop', 'paint']):
                    subject = 'Computer'
                elif any(kw in name_lower for kw in ['hygiene', 'posture', 'eating', 'physical', 'play']):
                    subject = 'Health'
                elif any(kw in name_lower for kw in ['sharing', 'honesty', 'kindness', 'teamwork', 'empathy']):
                    subject = 'Moral Science'
                elif any(kw in name_lower for kw in ['landmarks', 'symbols', 'solar system', 'continents']):
                    subject = 'GK'
                else:
                    # Cannot determine - skip this topic
                    continue
        
        topics.append((clean_name, grade, subject))
    
    return topics

def build_curriculum(topics):
    """Build curriculum_canon.json structure from extracted topics."""
    # Group by (grade, subject)
    by_grade_subject = {}
    for name, grade, subject in topics:
        key = (grade, subject)
        by_grade_subject.setdefault(key, []).append(name)
    
    # Build curriculum JSON
    curriculum = {
        "meta": {
            "version": "3.1",
            "generated_from": "slot_engine.py TOPIC_PROFILES",
            "description": "Auto-synced curriculum - only topics with working generation logic",
            "last_synced": "Run: python backend/scripts/sync_curriculum.py"
        },
        "grades": []
    }
    
    for grade_num in sorted(set(g for g, _ in by_grade_subject.keys())):
        subjects_data = []
        
        # Sort subjects for consistent ordering
        subject_order = ['Maths', 'English', 'EVS', 'Science', 'Hindi', 'Computer', 'GK', 'Health', 'Moral Science']
        subjects_in_grade = sorted(
            set(s for g, s in by_grade_subject.keys() if g == grade_num),
            key=lambda s: subject_order.index(s) if s in subject_order else 999
        )
        
        for subject in subjects_in_grade:
            topics_list = sorted(set(by_grade_subject[(grade_num, subject)]))
            
            # CRITICAL FIX: Use subject-appropriate logic_tags
            logic_tags = SUBJECT_LOGIC_TAGS.get(subject, ['observation'])
            
            subjects_data.append({
                "name": subject,
                "region": "Global",
                "skills": topics_list,
                "logic_tags": logic_tags,
                "depth": "core"
            })
        
        curriculum["grades"].append({
            "grade": grade_num,
            "stage": "Foundational" if grade_num <= 2 else "Preparatory",
            "subjects": subjects_data
        })
    
    return curriculum

def main():
    """Main sync execution."""
    print("=" * 60)
    print("CURRICULUM SYNC - PRODUCTION RUN")
    print("=" * 60)
    
    print("\n🔍 Step 1: Extracting topics from slot_engine.py...")
    topics = extract_topics_from_slot_engine()
    print(f"   ✓ Found {len(topics)} topics with working generation logic")
    
    # Show breakdown by grade and subject
    by_gs = {}
    for _, g, s in topics:
        key = (g, s)
        by_gs[key] = by_gs.get(key, 0) + 1
    
    print("\n📊 Step 2: Topics by Grade and Subject:")
    for grade in sorted(set(g for g, _ in by_gs.keys())):
        subjects_in_grade = [(s, by_gs[(grade, s)]) for g, s in sorted(by_gs.keys()) if g == grade]
        print(f"\n   Class {grade}:")
        for subj, count in subjects_in_grade:
            print(f"      {subj:20} {count} topics")
    
    # Validation checks
    print("\n✅ Step 3: Validation checks:")
    
    maths_count = sum(1 for _, _, s in topics if s == 'Maths')
    print(f"   ✓ Maths topics: {maths_count} (should be 9+)")
    
    evs_count = sum(1 for _, g, s in topics if s == 'EVS' and g in [1, 2])
    science_count_c12 = sum(1 for _, g, s in topics if s == 'Science' and g in [1, 2])
    print(f"   ✓ EVS topics (Class 1/2): {evs_count}")
    if science_count_c12 > 0:
        print(f"   ⚠️  WARNING: {science_count_c12} Class 1/2 topics still labeled 'Science' instead of 'EVS'")
    else:
        print(f"   ✓ No Class 1/2 Science topics (correct - should all be EVS)")
    
    # Check for missing critical topics
    c1_maths = [name for name, g, s in topics if g == 1 and s == 'Maths']
    expected_c1_maths = ['Numbers 1 to 50', 'Numbers 51 to 100', 'Addition up to 20', 'Subtraction within 20']
    missing = [t for t in expected_c1_maths if t not in c1_maths]
    if missing:
        print(f"   ⚠️  Missing Class 1 Maths topics: {missing}")
    else:
        print(f"   ✓ All core Class 1 Maths topics present")
    
    print("\n🔨 Step 4: Building curriculum_canon.json...")
    curriculum = build_curriculum(topics)
    
    print(f"   ✓ Generated {len(curriculum['grades'])} grades")
    print(f"   ✓ Total subjects: {sum(len(g['subjects']) for g in curriculum['grades'])}")
    
    print(f"\n📝 Step 5: Writing to {CURRICULUM_PATH.relative_to(BACKEND_DIR)}...")
    with open(CURRICULUM_PATH, 'w') as f:
        json.dump(curriculum, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS - curriculum_canon.json synced")
    print("=" * 60)
    print("\n📋 NEXT STEPS:")
    print("   1. Restart backend to reload curriculum")
    print("   2. Test: Open generator, check dropdown shows correct topics")
    print("   3. Verify: Science topics for Class 1/2 show as 'EVS'")
    print("   4. Verify: Science topics have logic_tags = ['observation', ...] not ['numerical']")
    print("\n   Then commit:")
    print("   git add backend/app/data/curriculum_canon.json backend/scripts/sync_curriculum.py")
    print('   git commit -m "Fix curriculum: EVS for C1/2, correct logic_tags, sync from slot_engine"')
    print("   git push")
    print()

if __name__ == "__main__":
    main()
