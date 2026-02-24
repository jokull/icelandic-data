#!/usr/bin/env python3
import json
import sys
from datetime import datetime
from planitor.database import db_context
from planitor.crud import get_or_create_council, get_or_create_meeting, get_or_create_municipality, create_minute, get_or_create_attachment
from planitor.models import Minute

COUNCIL_MAPPING = {
    "Afgreiðslufundir skipulagsfulltrúa": ("reykjavik", "skipulagsfulltrui", "Skipulagsfulltrúi"),
    "Skipulags- og samgönguráð": ("reykjavik", "skipulagsrad", "Skipulags- og samgönguráð"),
}

data = json.load(sys.stdin)
md = data["meeting"]
muni_slug, council_slug, council_label = COUNCIL_MAPPING.get(md["council"], ("reykjavik", "unknown", md["council"]))
attendees = md.get("attendees", [])
desc = "Fundur nr. " + str(md["number"])
if attendees:
    desc += ". Þessi sátu fundinn: " + ", ".join(attendees) + "."

with db_context() as db:
    muni, _ = get_or_create_municipality(db, muni_slug)
    db.commit()
    council, _ = get_or_create_council(db, muni, slug=council_slug, label=council_label)
    db.commit()
    meeting, created = get_or_create_meeting(db, council, str(md["number"]))
    if not created:
        existing = db.query(Minute).filter(Minute.meeting == meeting).count()
        if existing:
            print("Skip " + str(md["number"]) + " (" + str(existing) + " exist)")
            sys.exit(0)
    meeting.url = md.get("url", "")
    meeting.description = desc
    meeting.attendant_names = attendees
    meeting.start = datetime.fromisoformat(md["date"]) if md.get("date") else datetime.now()
    db.commit()
    
    minute_count = 0
    attachment_count = 0
    for i, m in enumerate(data.get("minutes", []), 1):
        try:
            minute = create_minute(
                db, meeting,
                serial=str(i),
                case_serial=m.get("case_serial") or ("F" + str(md["number"]) + "-" + str(i)),
                case_address=m.get("address") or "",
                headline=(m.get("headline") or "")[:500],
                inquiry=m.get("inquiry") or "",
                remarks=m.get("remarks") or ""
            )
            db.commit()
            minute_count += 1
            
            # Create attachments
            for att in m.get("attachments", []):
                attachment, _ = get_or_create_attachment(
                    db, minute,
                    url=att["url"],
                    label=att.get("label", "Attachment"),
                    type=att.get("type", "application/pdf")
                )
                db.commit()
                attachment_count += 1
        except Exception as e:
            print("Error minute " + str(i) + ": " + str(e))
            db.rollback()
    
    print("Imported " + str(md["number"]) + ": " + str(minute_count) + " minutes, " + str(attachment_count) + " attachments")
