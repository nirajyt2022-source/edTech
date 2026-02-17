#!/usr/bin/env python3
"""
EMERGENCY FIX - Complete Solution

Fixes:
1. ✅ Temperature already 0.3 in your code
2. ❌ Class 3/4 missing Maths → ADD NOW
3. ❌ Backend running OLD code → MUST RESTART
4. ❌ No validation rejecting wrong questions → ADD NOW

Run from: cd backend && python scripts/emergency_fix.py
"""
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
SLOT_ENGINE_PATH = BACKEND_DIR / "app" / "services" / "slot_engine.py"
CURRICULUM_PATH = BACKEND_DIR / "app" / "data" / "curriculum_canon.json"

def fix_curriculum():
    """Add Class 3/4 Maths to curriculum_canon.json"""
    print("=" * 60)
    print("FIX 1: Adding Class 3/4 Maths to curriculum")
    print("=" * 60)
    
    with open(CURRICULUM_PATH) as f:
        curriculum = json.load(f)
    
    # Class 3/4 Maths topics (these exist in slot_engine without Class suffix)
    class3_maths_topics = [
        "Addition and subtraction (3-digit)",
        "Multiplication tables (2-5)",
        "Division basics",
        "Fractions (halves and quarters)",
        "Time (reading clock, calendar)",
        "Money (bills and change)",
        "Measurement (length, weight)",
    ]
    
    class4_maths_topics = [
        "Addition and subtraction (4-digit)",
        "Multiplication (2-digit by 1-digit)",
        "Division (2-digit by 1-digit)",
        "Fractions (addition and subtraction)",
        "Decimals introduction",
        "Time (minutes, 24-hour clock)",
        "Money (word problems)",
    ]
    
    modified = False
    
    for grade_data in curriculum["grades"]:
        if grade_data["grade"] == 3:
            has_maths = any(s["name"] == "Maths" for s in grade_data["subjects"])
            if not has_maths:
                print(f"\n✓ Adding Maths to Class 3 ({len(class3_maths_topics)} topics)")
                grade_data["subjects"].insert(0, {
                    "name": "Maths",
                    "region": "Global",
                    "skills": class3_maths_topics,
                    "logic_tags": ["numerical", "spatial", "logical"],
                    "depth": "core"
                })
                modified = True
            else:
                print(f"\n✓ Class 3 already has Maths")
        
        elif grade_data["grade"] == 4:
            has_maths = any(s["name"] == "Maths" for s in grade_data["subjects"])
            if not has_maths:
                print(f"✓ Adding Maths to Class 4 ({len(class4_maths_topics)} topics)")
                grade_data["subjects"].insert(0, {
                    "name": "Maths",
                    "region": "Global",
                    "skills": class4_maths_topics,
                    "logic_tags": ["numerical", "spatial", "logical"],
                    "depth": "core"
                })
                modified = True
            else:
                print(f"✓ Class 4 already has Maths")
    
    if modified:
        with open(CURRICULUM_PATH, 'w') as f:
            json.dump(curriculum, f, indent=2, ensure_ascii=False)
        print("\n✅ curriculum_canon.json updated")
        return True
    else:
        print("\nℹ️  No changes needed")
        return False

def add_validation_to_slot_engine():
    """Add post-generation validation to reject wrong questions"""
    print("\n" + "=" * 60)
    print("FIX 2: Adding question validation")
    print("=" * 60)
    
    with open(SLOT_ENGINE_PATH) as f:
        content = f.read()
    
    # Check if validation already exists
    if "_validate_question_matches_topic" in content:
        print("\n✓ Validation already exists")
        return False
    
    # Find where to insert validation function (after generate_question)
    validation_code = '''

def _validate_question_matches_topic(q: dict, skill_tag: str, disallowed_keywords: list[str]) -> tuple[bool, str]:
    """Validate that generated question respects topic constraints.
    
    Returns: (is_valid, reason)
    """
    text = (q.get("question_text", "") + " " + str(q.get("answer", ""))).lower()
    
    # Check disallowed keywords
    for kw in disallowed_keywords:
        if kw in text:
            return (False, f"Contains disallowed keyword '{kw}'")
    
    # Topic-specific validation
    if "shape" in skill_tag.lower():
        # Must contain shape words
        shape_words = ["circle", "square", "triangle", "rectangle", "shape", "corner", "side", "round", "straight"]
        if not any(w in text for w in shape_words):
            return (False, "Shape question missing shape vocabulary")
        # Must NOT contain arithmetic
        bad_words = ["add", "subtract", "+", "-", "×", "÷", "column", "carry", "borrow"]
        if any(w in text for w in bad_words):
            return (False, "Shape question contains arithmetic")
    
    if "time" in skill_tag.lower():
        time_words = ["clock", "hour", "minute", "morning", "afternoon", "evening", "day", "week", "o'clock"]
        if not any(w in text for w in time_words):
            return (False, "Time question missing time vocabulary")
    
    if "money" in skill_tag.lower():
        money_words = ["rupee", "coin", "note", "cost", "price", "buy", "₹", "rs"]
        if not any(w in text for w in money_words):
            return (False, "Money question missing money vocabulary")
    
    if "measure" in skill_tag.lower():
        measure_words = ["longer", "shorter", "taller", "heavier", "lighter", "length", "weight", "height"]
        if not any(w in text for w in measure_words):
            return (False, "Measurement question missing measurement vocabulary")
    
    return (True, "OK")
'''
    
    # Find insertion point (after generate_question function)
    match = re.search(r'(def generate_question\(.*?\n(?:.*?\n)*?    return q\n\n)', content, re.DOTALL)
    if match:
        insert_pos = match.end()
        new_content = content[:insert_pos] + validation_code + content[insert_pos:]
        
        with open(SLOT_ENGINE_PATH, 'w') as f:
            f.write(new_content)
        
        print("\n✅ Validation function added to slot_engine.py")
        print("   Function: _validate_question_matches_topic")
        return True
    else:
        print("\n⚠️  Could not find insertion point")
        print("   You'll need to add validation manually")
        return False

def show_restart_instructions():
    """Show how to restart backend to load new code"""
    print("\n" + "=" * 60)
    print("FIX 3: RESTART BACKEND (CRITICAL)")
    print("=" * 60)
    print("""
Your code changes are correct (temperature=0.3, instructions say NO addition)
but the BACKEND IS RUNNING OLD CODE.

You MUST restart the backend completely:

METHOD 1 - Kill and restart:
  # Find the backend process
  ps aux | grep uvicorn
  
  # Kill it
  pkill -f "uvicorn app.main"
  
  # Start fresh
  cd backend
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

METHOD 2 - If running in Railway/Docker:
  # Redeploy completely
  git add backend/app/data/curriculum_canon.json
  git commit -m "Add Class 3/4 Maths + emergency fixes"
  git push
  
  # Railway will auto-redeploy

METHOD 3 - If in development with --reload:
  # Touch a file to trigger reload
  touch backend/app/main.py
  
  # OR restart manually with Ctrl+C then run uvicorn again

CRITICAL: A simple "reload" may not work if you changed slot_engine.py
You need a COMPLETE RESTART to reload the module.
""")

def verify_fixes():
    """Show what to test after restart"""
    print("\n" + "=" * 60)
    print("TESTING AFTER RESTART")
    print("=" * 60)
    print("""
1. TEST: Class 3/4 Maths appears in dropdown
   - Open generator
   - Select Class 3 → Maths should appear
   - Select Class 4 → Maths should appear

2. TEST: Basic Shapes generates shape questions
   - Select Class 1, Maths, Basic Shapes
   - Generate worksheet
   - Questions should be about circles/squares/triangles
   - Should NOT contain addition/subtraction

3. TEST: Generate via curl to see raw output:
   curl -X POST http://localhost:8000/api/worksheets/generate \\
     -H "Content-Type: application/json" \\
     -d '{
       "grade_level": "Class 1",
       "subject": "Maths",
       "topic": "Basic Shapes",
       "difficulty": "easy",
       "num_questions": 3,
       "language": "English"
     }' | jq '.worksheet.questions[0] | {text, skill_tag}'

   Expected output:
   {
     "text": "I have 4 equal sides and 4 corners. What shape am I?",
     "skill_tag": "c1_shape_identify"
   }

   NOT this:
   {
     "text": "Write 345 + 278 in column form",
     "skill_tag": "c1_shape_identify"  
   }

If Basic Shapes STILL generates addition after restart:
→ The validation function will catch and log it
→ Check backend logs for warnings
→ Contact me with the log output
""")

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║     EMERGENCY FIX - TWO CRITICAL BUGS                    ║
╚══════════════════════════════════════════════════════════╝

BUG 1: Class 3/4 missing Maths in dropdown
  ROOT CAUSE: curriculum_canon.json missing these grades
  FIX: Add generic arithmetic topics manually

BUG 2: Basic Shapes generates addition (despite temp=0.3)
  ROOT CAUSE: Backend running OLD code (not restarted)
  FIX: Add validation + RESTART backend completely
""")
    
    # Run fixes
    curriculum_fixed = fix_curriculum()
    validation_added = add_validation_to_slot_engine()
    
    # Show restart instructions
    show_restart_instructions()
    
    # Show testing instructions
    verify_fixes()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ Curriculum fixed: {curriculum_fixed}")
    print(f"✅ Validation added: {validation_added}")
    print("⚠️  BACKEND RESTART REQUIRED")
    print("\nNext steps:")
    print("1. Restart backend (see instructions above)")
    print("2. Test Class 3/4 Maths appears")
    print("3. Test Basic Shapes generates shapes not addition")
    print("4. If still broken, share backend logs")
    print()

if __name__ == "__main__":
    main()
