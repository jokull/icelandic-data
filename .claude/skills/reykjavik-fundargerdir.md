# Reykjavík Fundargerðir (Meeting Minutes)

Scrapes meeting minutes from Reykjavík municipality for planning and building permits.

## Data Scope

Meeting minutes from three councils relevant to planitor.io:

| Council | URL Pattern | Content |
|---------|-------------|---------|
| Afgreiðslufundir skipulagsfulltrúa | `/fundargerdir/afgreidslufundir-skipulagsfulltrua-fundur-nr-{N}` | Planning officer decisions |
| Umhverfis- og skipulagsráð | `/fundargerdir/umhverfis-og-skipulagsrad-fundur-nr-{N}` | Environment & Planning board |
| Byggingarfulltrúi | `/byggingarmal/fundargerdir-byggingarfulltrua` | Building permits (JS-rendered) |

## Base URLs

- Main site: `https://reykjavik.is`
- Meeting list: `https://reykjavik.is/fundargerdir`
- PDF attachments: `https://fundur.reykjavik.is/sites/default/files/agenda-items/`

## Meeting Page Structure

Each meeting page contains:
- Meeting number and date
- Attendees (fundarmenn)
- Agenda items with:
  - Case reference (e.g., `USK26020145`)
  - Address/location
  - Applicant names (kennitalas scrubbed in HTML)
  - Decision text
  - PDF attachment links

## Fetching Meetings

### List recent meetings
```bash
curl -s "https://reykjavik.is/fundargerdir" | grep -o '/fundargerdir/[^"]*skipulagsfulltrua[^"]*'
```

### Fetch specific meeting
```bash
curl -s "https://reykjavik.is/fundargerdir/afgreidslufundir-skipulagsfulltrua-fundur-nr-1049"
```

### Extract PDF URLs from meeting page
```bash
curl -s "https://reykjavik.is/fundargerdir/afgreidslufundir-skipulagsfulltrua-fundur-nr-1049" | \
  grep -o 'https://fundur.reykjavik.is/[^"]*\.pdf'
```

## PDF Extraction

PDFs may contain kennitalas that are visually redacted but extractable as text.

```bash
# Extract text from PDF
pdftotext -layout document.pdf -

# Or with Python pdfplumber
uv run python -c "
import pdfplumber
with pdfplumber.open('document.pdf') as pdf:
    for page in pdf.pages:
        print(page.extract_text())
"
```

## Data Output

Output format compatible with planitor database:

```json
{
  "meeting": {
    "council": "Afgreiðslufundir skipulagsfulltrúa",
    "number": 1049,
    "date": "2026-02-17T09:10:00",
    "attendees": ["Brynjar Þór Jónasson", "Hjördís Sóley Sigurðardóttir"]
  },
  "minutes": [
    {
      "case_serial": "USK26020145",
      "headline": "1. lota Borgarlínu - Hlemmur - Laugavegur - Framkvæmdaleyfi",
      "address": "Laugavegur",
      "inquiry": "Lögð fram umsókn...",
      "remarks": "Samþykkt að gefa út framkvæmdaleyfi...",
      "entities": [
        {"name": "Betri Samgangna ohf.", "type": "company"}
      ],
      "attachments": [
        {"url": "https://fundur.reykjavik.is/...", "name": "Umsögn skipulagsfulltrúa"}
      ]
    }
  ]
}
```

## Known Issues

1. **Kennitalas scrubbed**: Personal/company IDs removed from HTML, may be in PDFs
2. **JS-rendered content**: Byggingarfulltrúi page needs browser automation
3. **Encoding**: Response is UTF-8
4. **Rate limiting**: Be respectful, add delays between requests

## Related

- Planitor scrapers: `/Users/jokull/mediaserver/planitor/scrape/spiders/`
- Old source (dead): `gamli.rvk.is`
