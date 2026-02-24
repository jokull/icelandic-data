#!/usr/bin/env python3
"""Import scraped fundargerðir JSON files into planitor database."""
import json
import sys
from datetime import datetime
from pathlib import Path
from planitor.database import db_context
from planitor.crud import get_or_create_council, get_or_create_meeting, get_or_create_municipality, create_minute
from planitor.models import Minute

COUNCIL_MAPPING = {
    "Afgreiðslufundir skipulagsfulltrúa": ("reykjavik", "skipulagsfulltrui", "Skipulagsfulltrúi"),
    "Skipulags- og samgönguráð": ("reykjavik", "skipulagsrad", "Skipulags- og samgönguráð"),
}

def import_file(filepath: str):
    """Import a single JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    md = data["meeting"]
    council_name = md.get("council", "")
    mapping = COUNCIL_MAPPING.get(council_name, ("reykjavik", "unknown", council_name))
    muni_slug, council_slug, council_label = mapping
    
    attendees = md.get("attendees", [])
    number = md["number"]
    desc = f"Fundur nr. {number}"
    if attendees:
        desc += f". Þessi sátu fundinn: {', '.join(attendees)}."
    
    with db_context() as db:
        muni, _ = get_or_create_municipality(db, muni_slug)
        db.commit()
        council, _ = get_or_create_council(db, muni, slug=council_slug, label=council_label)
        db.commit()
        meeting, created = get_or_create_meeting(db, council, str(number))
        
        if not created:
            existing = db.query(Minute).filter(Minute.meeting == meeting).count()
            if existing:
                print(f"Skip {number} ({existing} exist)")
                return 0
        
        meeting.url = md.get("url", "")
        meeting.description = desc
        meeting.attendant_names = attendees
        if md.get("date"):
            meeting.start = datetime.fromisoformat(md["date"])
        else:
            meeting.start = datetime.now()
        db.commit()
        
        count = 0
        for i, m in enumerate(data.get("minutes", []), 1):
            try:
                case_serial = m.get("case_serial") or f"F{number}-{i}"
                headline = (m.get("headline") or "")[:500]
                create_minute(
                    db, meeting,
                    serial=str(i),
                    case_serial=case_serial,
                    case_address=m.get("address") or "",
                    headline=headline,
                    inquiry=m.get("inquiry") or "",
                    remarks=m.get("remarks") or ""
                )
                db.commit()
                count += 1
            except Exception as e:
                db.rollback()
                print(f"  Error on minute {i}: {e}")
        
        print(f"Imported {number}: {count} minutes")
        return count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_fundargerdir.py <json_file_or_dir>")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    total = 0
    
    if path.is_dir():
        for f in sorted(path.glob("*.json")):
            total += import_file(str(f))
    else:
        total += import_file(str(path))
    
    print(f"\nTotal minutes imported: {total}")
