"""
Import scraped fundargerðir into planitor database.

Usage:
    uv run python scripts/import_to_planitor.py <json_file> [--dry-run]
    uv run python scripts/import_to_planitor.py data/raw/reykjavik-fundargerdir/skipulagsfulltrui_896.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import typer

app = typer.Typer()

# Map our council names to planitor slugs
COUNCIL_MAPPING = {
    "Afgreiðslufundir skipulagsfulltrúa": {
        "municipality_slug": "reykjavik",
        "council_slug": "skipulagsfulltrui",
        "council_label": "Skipulagsfulltrúi",
    },
    "Skipulags- og samgönguráð": {
        "municipality_slug": "reykjavik",
        "council_slug": "skipulagsrad",
        "council_label": "Skipulags- og samgönguráð",
    },
    "Umhverfis- og skipulagsráð": {
        "municipality_slug": "reykjavik",
        "council_slug": "umhverfis-og-skipulagsrad",
        "council_label": "Umhverfis- og skipulagsráð",
    },
}


def convert_to_planitor_format(data: dict) -> dict:
    """Convert our JSON format to planitor's scrapy item format."""
    meeting = data["meeting"]
    council_name = meeting["council"]
    
    mapping = COUNCIL_MAPPING.get(council_name, {
        "municipality_slug": "reykjavik",
        "council_slug": council_name.lower().replace(" ", "-"),
        "council_label": council_name,
    })
    
    # Build description from attendees
    attendees = meeting.get("attendees", [])
    description = f"Fundur nr. {meeting['number']}"
    if attendees:
        description += f". Þessi sátu fundinn: {', '.join(attendees)}."
    
    # Convert minutes
    minutes = []
    for i, m in enumerate(data.get("minutes", []), 1):
        minute = {
            "serial": str(i),
            "case_serial": m.get("case_serial") or f"F{meeting['number']}-{i}",
            "case_address": m.get("address") or "",
            "headline": m.get("headline", "")[:500],
            "inquiry": m.get("inquiry") or "",
            "remarks": m.get("remarks") or "",
        }
        
        # Add entity info to inquiry if present
        entities = m.get("entities", [])
        if entities:
            entity_names = [e["name"] for e in entities]
            if minute["inquiry"]:
                minute["inquiry"] += f"\n\nUmsækjendur: {', '.join(entity_names)}"
        
        minutes.append(minute)
    
    return {
        "municipality_slug": mapping["municipality_slug"],
        "council_type_slug": mapping["council_slug"],
        "council_label": mapping["council_label"],
        "url": meeting.get("url", ""),
        "name": str(meeting["number"]),
        "start": datetime.fromisoformat(meeting["date"]) if meeting.get("date") else datetime.now(),
        "description": description,
        "attendant_names": attendees,
        "minutes": minutes,
    }


def import_to_database(item: dict, dry_run: bool = False):
    """Import a single meeting item to planitor database."""
    # Import planitor modules
    sys.path.insert(0, "/Users/jokull/mediaserver/planitor")
    os.environ.setdefault("DATABASE_URL", "postgresql://planitor:password@localhost:5432/planitor")
    
    from planitor.database import db_context
    from planitor.crud import (
        get_or_create_council,
        get_or_create_meeting,
        get_or_create_municipality,
    )
    from planitor.models import Minute
    from planitor.postprocess import process_minutes
    
    with db_context() as db:
        # Get or create municipality
        muni, created = get_or_create_municipality(db, item["municipality_slug"])
        if created:
            db.commit()
            print(f"  Created municipality: {item['municipality_slug']}")
        
        # Get or create council
        council, created = get_or_create_council(
            db,
            muni,
            slug=item["council_type_slug"],
            label=item.get("council_label"),
        )
        if created:
            db.commit()
            print(f"  Created council: {item['council_type_slug']}")
        
        # Get or create meeting
        meeting, created = get_or_create_meeting(db, council, item["name"])
        
        if not created:
            # Check if meeting already has minutes
            existing_minutes = db.query(Minute).filter(Minute.meeting == meeting).count()
            if existing_minutes:
                print(f"  Meeting {item['name']} already has {existing_minutes} minutes, skipping")
                return False
        
        if dry_run:
            print(f"  [DRY RUN] Would create meeting {item['name']} with {len(item['minutes'])} minutes")
            return True
        
        # Update meeting details
        meeting.url = item["url"]
        meeting.description = item["description"]
        meeting.attendant_names = item.get("attendant_names", [])
        meeting.start = item["start"]
        db.commit()
        
        print(f"  Created/updated meeting: {item['name']}")
        
        # Process minutes (this handles lemmatization, entity extraction, etc.)
        print(f"  Processing {len(item['minutes'])} minutes...")
        process_minutes(db, item["minutes"], meeting)
        
        print(f"  ✓ Imported meeting {item['name']} with {len(item['minutes'])} minutes")
        return True


@app.command()
def main(
    json_file: Path,
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't actually import"),
):
    """Import a scraped meeting JSON file into planitor database."""
    
    if not json_file.exists():
        typer.echo(f"File not found: {json_file}")
        raise typer.Exit(1)
    
    data = json.loads(json_file.read_text())
    
    typer.echo(f"Importing: {json_file.name}")
    typer.echo(f"  Council: {data['meeting']['council']}")
    typer.echo(f"  Meeting: #{data['meeting']['number']}")
    typer.echo(f"  Date: {data['meeting']['date']}")
    typer.echo(f"  Minutes: {len(data.get('minutes', []))}")
    
    # Convert format
    item = convert_to_planitor_format(data)
    
    # Import
    try:
        success = import_to_database(item, dry_run=dry_run)
        if success:
            typer.echo("✓ Import complete")
        else:
            typer.echo("⚠ Import skipped (already exists)")
    except Exception as e:
        typer.echo(f"✗ Import failed: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
