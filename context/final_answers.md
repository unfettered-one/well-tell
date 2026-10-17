{
  "dataset_id": "test",
  "as_of": "2027-01-15",
  "answers": [
    {
      "question_id": "Q1",
      "user": "Michael Turner",
      "question": "All our wells feed one reservoir. Map the reservoir pressure across the field from the pressure data.",
      "response": {
        "session_id": "chat-35c87dcb54e04fc29080c249fa513552",
        "answer": "I can’t map reservoir pressure from this dataset: its inspection records contain temperature and spill measurements, but no pressure readings. Well coordinates are available, but without pressure values a pressure map would be misleading. If you provide or identify pressure measurements, I can map them across the field.",
        "citations": [],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q2",
      "user": "Robert Hayes",
      "question": "Which well produced the most oil in 2026?",
      "response": {
        "session_id": "chat-4dcfa7dbeb54494f9fd6418209daecda",
        "answer": "I can’t determine that from this dataset: it contains no oil-production volume records for 2026, so I can’t identify the top-producing well.",
        "citations": [],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q3",
      "user": "Laura Simmons",
      "question": "Since 1 Nov 2026, every time an operator note reports gas at a well, did we get someone out to that well in time under our operating procedures? List every report and whether the response met the deadline.",
      "response": {
        "session_id": "chat-234bd686b4bf4b6681a0e25fb38866c5",
        "answer": "**17 of 26 gas-odor operator notes met the response deadline; 9 missed.** I counted a response only if a maintenance job started or a manual inspection occurred at that well after the note. The Operations SOP allows 24 hours for notes before 1 Jan 2027 and 12 hours from that date; times below are UTC. “No response recorded” means no subsequent qualifying response was found through the dataset’s as-of date, 15 Jan 2027. [fleet/sops/operations-sop-rev2.md]\n\n| Operator note | Well | Response (time; elapsed) | Result |\n|---|---|---|---|\n| CTX-0163-002 | WELL-0163 | MNT-0163-019 (14 Nov 2026 08:00; 251.1 h) | Missed—late |\n| CTX-0149-004 | WELL-0149 | MNT-0149-029 (7 Nov 2026 08:00; 13.7 h) | Met |\n| CTX-0165-001 | WELL-0165 | MNT-0165-031 (14 Nov 2026 08:00; 11.4 h) | Met |\n| CTX-0341-002 | WELL-0341 | INS-0341-0109 (17 Dec 2026 13:30; 677.8 h) | Missed—late |\n| CTX-0091-001 | WELL-0091 | MNT-0091-019 (28 Nov 2026 08:00; 9.6 h) | Met |\n| CTX-0423-002 | WELL-0423 | INS-0423-0213 (3 Dec 2026 09:15; 3.8 h) | Met |\n| CTX-0059-002 | WELL-0059 | INS-0059-0213 (3 Dec 2026 12:15; 6.1 h) | Met |\n| CTX-0332-004 | WELL-0332 | No qualifying response recorded | Missed—none recorded |\n| CTX-0401-002 | WELL-0401 | MNT-0401-033 (11 Dec 2026 08:00; 138.2 h) | Missed—late |\n| CTX-0189-003 | WELL-0189 | MNT-0189-037 (11 Dec 2026 08:00; 19.4 h) | Met |\n| CTX-0403-004 | WELL-0403 | MNT-0403-024 (11 Dec 2026 08:00; 10.8 h) | Met |\n| CTX-0244-002 | WELL-0244 | MNT-0244-026 (11 Dec 2026 08:00; 2.6 h) | Met |\n| CTX-0040-002 | WELL-0040 | MNT-0040-029 (12 Dec 2026 08:00; 6.1 h) | Met |\n| CTX-0228-004 | WELL-0228 | INS-0228-0144 (17 Dec 2026 12:45; 16.9 h) | Met |\n| CTX-0052-003 | WELL-0052 | No qualifying response recorded | Missed—none recorded |\n| CTX-0370-005 | WELL-0370 | MNT-0370-028 (22 Dec 2026 08:00; 19.3 h) | Met |\n| CTX-0362-002 | WELL-0362 | MNT-0362-030 (25 Dec 2026 08:00; 31.8 h) | Missed—late |\n| CTX-0161-006 | WELL-0161 | INS-0161-0168 (14 Jan 2027 11:00; 475.3 h) | Missed—late |\n| CTX-0135-009 | WELL-0135 | MNT-0135-034 (27 Dec 2026 08:00; 4.2 h) | Met |\n| CTX-0324-001 | WELL-0324 | MNT-0324-036 (2 Jan 2027 08:00; 9.3 h) | Met |\n| CTX-0330-003 | WELL-0330 | MNT-0330-030 (3 Jan 2027 08:00; 10.3 h) | Met |\n| CTX-0599-003 | WELL-0599 | INS-0599-0196 (7 Jan 2027 09:45; 16.4 h) | Missed—late |\n| CTX-0516-002 | WELL-0516 | INS-0516-0215 (7 Jan 2027 12:15; 15.0 h) | Missed—late |\n| CTX-0425-006 | WELL-0425 | INS-0425-0218 (7 Jan 2027 09:00; 3.7 h) | Met |\n| CTX-0465-005 | WELL-0465 | MNT-0465-031 (9 Jan 2027 08:00; 8.4 h) | Met |\n| CTX-0137-004 | WELL-0137 | MNT-0137-032 (11 Jan 2027 08:00; 8.5 h) | Met |",
        "citations": [
          "fleet/sops/operations-sop-rev2.md",
          "CTX-0163-002",
          "MNT-0163-019",
          "CTX-0149-004",
          "MNT-0149-029",
          "CTX-0165-001",
          "MNT-0165-031",
          "CTX-0341-002",
          "INS-0341-0109",
          "CTX-0091-001",
          "MNT-0091-019",
          "CTX-0423-002",
          "INS-0423-0213",
          "CTX-0059-002",
          "INS-0059-0213",
          "CTX-0332-004",
          "CTX-0401-002",
          "MNT-0401-033",
          "CTX-0189-003",
          "MNT-0189-037",
          "CTX-0403-004",
          "MNT-0403-024",
          "CTX-0244-002",
          "MNT-0244-026",
          "CTX-0040-002",
          "MNT-0040-029",
          "CTX-0228-004",
          "INS-0228-0144",
          "CTX-0052-003",
          "CTX-0370-005",
          "MNT-0370-028",
          "CTX-0362-002",
          "MNT-0362-030",
          "CTX-0161-006",
          "INS-0161-0168",
          "CTX-0135-009",
          "MNT-0135-034",
          "CTX-0324-001",
          "MNT-0324-036",
          "CTX-0330-003",
          "MNT-0330-030",
          "CTX-0599-003",
          "INS-0599-0196",
          "CTX-0516-002",
          "INS-0516-0215",
          "CTX-0425-006",
          "INS-0425-0218",
          "CTX-0465-005",
          "MNT-0465-031",
          "CTX-0137-004",
          "MNT-0137-032"
        ],
        "visual": {
          "type": "table",
          "title": "Gas-odor operator note response deadlines",
          "data": [
            {
              "note_id": "CTX-0163-002",
              "well": "WELL-0163",
              "response_id": "MNT-0163-019",
              "response_time_utc": "2026-11-14 08:00",
              "elapsed_hours": 251.1,
              "deadline_hours": 24,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0149-004",
              "well": "WELL-0149",
              "response_id": "MNT-0149-029",
              "response_time_utc": "2026-11-07 08:00",
              "elapsed_hours": 13.7,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0165-001",
              "well": "WELL-0165",
              "response_id": "MNT-0165-031",
              "response_time_utc": "2026-11-14 08:00",
              "elapsed_hours": 11.4,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0341-002",
              "well": "WELL-0341",
              "response_id": "INS-0341-0109",
              "response_time_utc": "2026-12-17 13:30",
              "elapsed_hours": 677.8,
              "deadline_hours": 24,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0091-001",
              "well": "WELL-0091",
              "response_id": "MNT-0091-019",
              "response_time_utc": "2026-11-28 08:00",
              "elapsed_hours": 9.6,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0423-002",
              "well": "WELL-0423",
              "response_id": "INS-0423-0213",
              "response_time_utc": "2026-12-03 09:15",
              "elapsed_hours": 3.8,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0059-002",
              "well": "WELL-0059",
              "response_id": "INS-0059-0213",
              "response_time_utc": "2026-12-03 12:15",
              "elapsed_hours": 6.1,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0332-004",
              "well": "WELL-0332",
              "response_id": null,
              "response_time_utc": null,
              "elapsed_hours": null,
              "deadline_hours": 24,
              "result": "Missed—none recorded"
            },
            {
              "note_id": "CTX-0401-002",
              "well": "WELL-0401",
              "response_id": "MNT-0401-033",
              "response_time_utc": "2026-12-11 08:00",
              "elapsed_hours": 138.2,
              "deadline_hours": 24,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0189-003",
              "well": "WELL-0189",
              "response_id": "MNT-0189-037",
              "response_time_utc": "2026-12-11 08:00",
              "elapsed_hours": 19.4,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0403-004",
              "well": "WELL-0403",
              "response_id": "MNT-0403-024",
              "response_time_utc": "2026-12-11 08:00",
              "elapsed_hours": 10.8,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0244-002",
              "well": "WELL-0244",
              "response_id": "MNT-0244-026",
              "response_time_utc": "2026-12-11 08:00",
              "elapsed_hours": 2.6,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0040-002",
              "well": "WELL-0040",
              "response_id": "MNT-0040-029",
              "response_time_utc": "2026-12-12 08:00",
              "elapsed_hours": 6.1,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0228-004",
              "well": "WELL-0228",
              "response_id": "INS-0228-0144",
              "response_time_utc": "2026-12-17 12:45",
              "elapsed_hours": 16.9,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0052-003",
              "well": "WELL-0052",
              "response_id": null,
              "response_time_utc": null,
              "elapsed_hours": null,
              "deadline_hours": 24,
              "result": "Missed—none recorded"
            },
            {
              "note_id": "CTX-0370-005",
              "well": "WELL-0370",
              "response_id": "MNT-0370-028",
              "response_time_utc": "2026-12-22 08:00",
              "elapsed_hours": 19.3,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0362-002",
              "well": "WELL-0362",
              "response_id": "MNT-0362-030",
              "response_time_utc": "2026-12-25 08:00",
              "elapsed_hours": 31.8,
              "deadline_hours": 24,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0161-006",
              "well": "WELL-0161",
              "response_id": "INS-0161-0168",
              "response_time_utc": "2027-01-14 11:00",
              "elapsed_hours": 475.3,
              "deadline_hours": 24,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0135-009",
              "well": "WELL-0135",
              "response_id": "MNT-0135-034",
              "response_time_utc": "2026-12-27 08:00",
              "elapsed_hours": 4.2,
              "deadline_hours": 24,
              "result": "Met"
            },
            {
              "note_id": "CTX-0324-001",
              "well": "WELL-0324",
              "response_id": "MNT-0324-036",
              "response_time_utc": "2027-01-02 08:00",
              "elapsed_hours": 9.3,
              "deadline_hours": 12,
              "result": "Met"
            },
            {
              "note_id": "CTX-0330-003",
              "well": "WELL-0330",
              "response_id": "MNT-0330-030",
              "response_time_utc": "2027-01-03 08:00",
              "elapsed_hours": 10.3,
              "deadline_hours": 12,
              "result": "Met"
            },
            {
              "note_id": "CTX-0599-003",
              "well": "WELL-0599",
              "response_id": "INS-0599-0196",
              "response_time_utc": "2027-01-07 09:45",
              "elapsed_hours": 16.4,
              "deadline_hours": 12,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0516-002",
              "well": "WELL-0516",
              "response_id": "INS-0516-0215",
              "response_time_utc": "2027-01-07 12:15",
              "elapsed_hours": 15.0,
              "deadline_hours": 12,
              "result": "Missed—late"
            },
            {
              "note_id": "CTX-0425-006",
              "well": "WELL-0425",
              "response_id": "INS-0425-0218",
              "response_time_utc": "2027-01-07 09:00",
              "elapsed_hours": 3.7,
              "deadline_hours": 12,
              "result": "Met"
            },
            {
              "note_id": "CTX-0465-005",
              "well": "WELL-0465",
              "response_id": "MNT-0465-031",
              "response_time_utc": "2027-01-09 08:00",
              "elapsed_hours": 8.4,
              "deadline_hours": 12,
              "result": "Met"
            },
            {
              "note_id": "CTX-0137-004",
              "well": "WELL-0137",
              "response_id": "MNT-0137-032",
              "response_time_utc": "2027-01-11 08:00",
              "elapsed_hours": 8.5,
              "deadline_hours": 12,
              "result": "Met"
            }
          ],
          "columns": [
            {
              "field": "note_id",
              "label": "Operator note"
            },
            {
              "field": "well",
              "label": "Well"
            },
            {
              "field": "response_id",
              "label": "Response record"
            },
            {
              "field": "response_time_utc",
              "label": "Response time (UTC)",
              "format": "datetime"
            },
            {
              "field": "elapsed_hours",
              "label": "Elapsed time",
              "unit": "h",
              "format": "number",
              "decimals": 1
            },
            {
              "field": "deadline_hours",
              "label": "Deadline",
              "unit": "h",
              "format": "number",
              "decimals": 0
            },
            {
              "field": "result",
              "label": "Result"
            }
          ]
        },
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q4",
      "user": "Chris Dalton",
      "question": "Across all areas, which temporary flowline bypasses are in place right now, and is each one allowed? Also list any bypass, past or present, that stayed in after its approval ran out or was never approved at all.",
      "response": {
        "session_id": "chat-4d171b84b1184fc2994edcafbb9f00d5",
        "answer": "As of the dataset date (15 Jan 2027), the notes show **three bypasses still in place**:\n\n- **WELL-0248 — Southeast Block 31:** Allowed. It is covered by MOC-2026-031, whose expiry was extended to 28 Feb 2027 by MOC-2026-044. The latest bypass note says it was in place pending a replacement valve. [CTX-0248-002]\n- **WELL-0249 — Southeast Block 31:** Not currently authorized. It is covered by MOC-2026-036, which expired 15 Dec 2026; the installation note is dated 25 Nov and no removal is recorded in the bypass notes. [CTX-0249-002]\n- **WELL-0405 — Northwest Block 12:** No approval found. Its bypass installation is recorded, but WELL-0405 is not among the wells authorized by MOC-2026-031/044 or MOC-2026-036. [CTX-0405-003]\n\n**Past or present bypasses that remained after approval expired or lacked approval:** WELL-0249 remained after MOC-2026-036 expired; WELL-0405 has no matching approval in the reviewed MOCs. For context, other bypass notes show removal before the applicable approval expiry, including WELL-0284 and WELL-0461. [CTX-0284-003, CTX-0461-003]\n\nThis reflects recorded installation/removal notes and the three cataloged MOCs; the notes do not establish whether additional approvals exist outside those records.",
        "citations": [
          "CTX-0248-002",
          "CTX-0249-002",
          "CTX-0405-003",
          "CTX-0284-003",
          "CTX-0461-003",
          "fleet/sops/moc-2026-031.md",
          "fleet/sops/moc-2026-036.md",
          "fleet/sops/moc-2026-044.md"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q5",
      "user": "Michael Turner",
      "question": "The State Oil & Gas Commission wrote to us in November 2026 about spills. Which of our spills does the letter cover, and on which ones are we not compliant? Show me a table.",
      "response": {
        "session_id": "chat-82bdef9db55d41dd951efabea63098a5",
        "answer": "The November 2026 Commission records cover four spills. **Three are marked non-compliant** with the SR-01 reporting deadline; one met it. The deadline comparison is from the spill-obligation records, and the letter/event details are shown below.\n\n| Letter/event date | Well | Spill inspection | Commission record | Reporting compliance | Evidence |\n|---|---|---|---|---|---|\n| Nov 5, 2026 | WELL-0119 | INS-0119-0209 | Spill report filed | Met — 7 hours against a 12-hour limit | REG-0119-001 |\n| Nov 9, 2026 | WELL-0349 | INS-0349-0206 | Notice of violation | Breached — 29 hours against a 12-hour limit | REG-0349-002 |\n| Nov 27, 2026 | WELL-0494 | INS-0494-0209 | Spill report filed | Breached — 38 hours against a 12-hour limit | REG-0494-001 |\n| Nov 28, 2026 | WELL-0564 | INS-0564-0181 | Spill report filed | Breached — 55 hours against a 12-hour limit | REG-0564-001 |\n\nThese are the Commission events dated in November, matched to SR-01 reporting obligations. The underlying spill-related inspections are listed for identification.",
        "citations": [
          "REG-0119-001",
          "INS-0119-0209",
          "REG-0349-002",
          "INS-0349-0206",
          "REG-0494-001",
          "INS-0494-0209",
          "REG-0564-001",
          "INS-0564-0181"
        ],
        "visual": {
          "type": "table",
          "title": "November 2026 Commission spill records and reporting compliance",
          "data": [
            {
              "event_date": "2026-11-05",
              "well": "WELL-0119",
              "spill_inspection": "INS-0119-0209",
              "commission_record": "spill_report_filed",
              "compliance": "Met — 7 hours; 12-hour limit",
              "event_id": "REG-0119-001"
            },
            {
              "event_date": "2026-11-09",
              "well": "WELL-0349",
              "spill_inspection": "INS-0349-0206",
              "commission_record": "notice_of_violation",
              "compliance": "Breached — 29 hours; 12-hour limit",
              "event_id": "REG-0349-002"
            },
            {
              "event_date": "2026-11-27",
              "well": "WELL-0494",
              "spill_inspection": "INS-0494-0209",
              "commission_record": "spill_report_filed",
              "compliance": "Breached — 38 hours; 12-hour limit",
              "event_id": "REG-0494-001"
            },
            {
              "event_date": "2026-11-28",
              "well": "WELL-0564",
              "spill_inspection": "INS-0564-0181",
              "commission_record": "spill_report_filed",
              "compliance": "Breached — 55 hours; 12-hour limit",
              "event_id": "REG-0564-001"
            }
          ],
          "columns": [
            {
              "field": "event_date",
              "label": "Commission event date",
              "format": "date"
            },
            {
              "field": "well",
              "label": "Well"
            },
            {
              "field": "spill_inspection",
              "label": "Spill inspection"
            },
            {
              "field": "commission_record",
              "label": "Commission record type"
            },
            {
              "field": "compliance",
              "label": "SR-01 reporting compliance"
            },
            {
              "field": "event_id",
              "label": "Event ID"
            }
          ]
        },
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q6",
      "user": "Nathan Pierce",
      "question": "Across the whole field, not just my area, for which wells do the latest inspection and the operator notes disagree about whether the well is producing oil? For each one, what is its real status right now, and why?",
      "response": {
        "session_id": "chat-7427a4c546fa4ff7825e735e1ad1baf3",
        "answer": "Across the field, the current view identifies two clear disagreements between the latest inspection evidence and an operator note:\n\n- **WELL-0026 — not producing per the latest inspection.** The inspection says “Pump jack not moving,” while the operator note says it was put back on production after the repair crew finished. The view still classifies it as not producing and shows an open flowline-corrosion repair; the note does not establish that it is producing now (INS-0026-0216, CTX-0026-001, MNT-0026-034).\n- **WELL-0032 — not producing per the latest inspection.** The inspection says “Wellhead cold to touch,” while the operator note says it was brought back online after a pump change. The current view classifies it as not producing, so the note conflicts with the inspection-based status (INS-0032-0219, CTX-0032-006).\n\nThese are inspection-based current classifications, not a direct measurement of oil sales or flow. I compared the field-wide latest-inspection/current-status view with its latest operator context note; the conflict view did not identify producing-status disagreements on its own.",
        "citations": [
          "INS-0026-0216",
          "CTX-0026-001",
          "MNT-0026-034",
          "INS-0032-0219",
          "CTX-0032-006"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q7",
      "turn": 1,
      "user": "Robert Hayes",
      "question": "Over the last month the operators have written notes about wells that sound or behave wrong. Which of those wells haven't had a repair since? Rank the 10 most likely to need a repair in the next 90 days, other than a spill clean-up, and quote the notes as evidence.",
      "response": {
        "session_id": "chat-e9c7a97a27a04d2c8d66e594ec5b7c92",
        "answer": "I can identify wells with operator notes from the month before the dataset cutoff (2027-01-15) and check whether they had a corrective repair afterward, excluding spill clean-ups. For the top-10 ranking, should I use an evidence-based risk ranking from the notes and repair history, or only include wells whose records explicitly predict a repair within 90 days?",
        "citations": [],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q7",
      "turn": 2,
      "user": "Robert Hayes",
      "question": "Which three would you send a crew to first this week, and why?",
      "response": {
        "session_id": "chat-e9c7a97a27a04d2c8d66e594ec5b7c92",
        "answer": "Using the most recent operator notes available in the dataset (as of 2027-01-15), I’d prioritize **active shut-ins and leak reports** over noise or performance symptoms. This is a triage recommendation from the notes—not a confirmed diagnosis or dispatch order.\n\n1. **WELL-0355** — The operator found a stuffing-box leak and shut the well in: “Found WELL-0355 leaking at the stuffing box, shut the well in.” No later corrective repair appears in the repair view; its latest listed corrective repair was September 12, 2026 (spill-line work). [CTX-0355-004; MNT-0355-026]\n2. **WELL-0323** — Also shut in for a reported stuffing-box leak: “Shut-in WELL-0323 after the pumper reported a stuffing box leak.” No later corrective repair appears; the latest listed was April 29, 2026, replacing stuffing-box packing. [CTX-0323-002; MNT-0323-025]\n3. **WELL-0044** — Shut in with a suspected flowline leak at the wellhead: “Shut in WELL-0044 at the wellhead, flowline leak suspected.” Its repair history includes repeated flowline-leak work, most recently August 21, 2026; no later corrective repair appears. [CTX-0044-008; MNT-0044-036]\n\nThese three have direct leak/shut-in evidence, making them higher-priority checks than notes describing a running well with noise or an adjustment deferred to a future visit.",
        "citations": [
          "CTX-0355-004",
          "MNT-0355-026",
          "CTX-0323-002",
          "MNT-0323-025",
          "CTX-0044-008",
          "MNT-0044-036"
        ],
        "visual": {
          "type": "table",
          "title": "Suggested crew priorities from operator notes",
          "columns": [
            {
              "field": "rank",
              "label": "Priority",
              "format": "number"
            },
            {
              "field": "asset_id",
              "label": "Well"
            },
            {
              "field": "reason",
              "label": "Why prioritize"
            },
            {
              "field": "operator_note",
              "label": "Operator note"
            },
            {
              "field": "latest_listed_repair",
              "label": "Latest listed corrective repair"
            }
          ],
          "data": [
            {
              "rank": 1,
              "asset_id": "WELL-0355",
              "reason": "Leak reported; well shut in. No later corrective repair appears in the view.",
              "operator_note": "Found WELL-0355 leaking at the stuffing box, shut the well in.",
              "latest_listed_repair": "MNT-0355-026 — 2026-09-12"
            },
            {
              "rank": 2,
              "asset_id": "WELL-0323",
              "reason": "Reported stuffing-box leak; well shut in. No later corrective repair appears in the view.",
              "operator_note": "Shut-in WELL-0323 after the pumper reported a stuffing box leak.",
              "latest_listed_repair": "MNT-0323-025 — 2026-04-29"
            },
            {
              "rank": 3,
              "asset_id": "WELL-0044",
              "reason": "Suspected wellhead flowline leak; well shut in, with prior flowline-leak repairs in the record.",
              "operator_note": "Shut in WELL-0044 at the wellhead, flowline leak suspected.",
              "latest_listed_repair": "MNT-0044-036 — 2026-08-21"
            }
          ]
        },
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q8",
      "turn": 1,
      "session_group": "Nathan Pierce session 1",
      "user": "Nathan Pierce",
      "question": "WELL-0333's recalled pump was swapped out yesterday. The work order isn't in the system yet. Please count it as replaced from now on.",
      "response": {
        "session_id": "chat-754708383b7b4bb2b1db1cea7441443e",
        "answer": "Recorded as a shared fact: WELL-0333’s recalled pump was swapped out on 2026-10-16, and should be counted as replaced from then on. The work order is not yet in the system. Recorded by Nathan Pierce (FACT-0001).",
        "citations": [
          "FACT-0001"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_remember",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q8",
      "turn": 2,
      "session_group": "Nathan Pierce session 1",
      "user": "Nathan Pierce",
      "question": "Also, just for me: whenever you list wells, sort them by area and then by well ID, and show costs in thousands of dollars.",
      "response": {
        "session_id": "chat-754708383b7b4bb2b1db1cea7441443e",
        "answer": "Saved as your private preference: when listing wells, I’ll sort by area and then well ID, and show costs in thousands of dollars (MEM-0001).",
        "citations": [
          "MEM-0001"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_remember",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q8",
      "turn": 3,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "Which recalled pumps are still in the ground right now?",
      "response": {
        "session_id": "chat-4b6379cae60c48bcaf5d85e209978681",
        "answer": "As of the dataset cutoff (2027-01-15), these recalled Highline RP-175 pumps are still shown as the latest installed downhole pumps in the maintenance reports: **WELL-0031** (LOT-2409-A; MNT-0031-027), **WELL-0156** (LOT-2409-A; MNT-0156-027), **WELL-0160** (LOT-2409-C; MNT-0160-028), **WELL-0263** (LOT-2410-B; MNT-0263-033), **WELL-0305** (LOT-2409-A; MNT-0305-032), **WELL-0426** (LOT-2409-C; MNT-0426-030), **WELL-0428** (LOT-2410-B; MNT-0428-022), and **WELL-0577** (LOT-2409-A; MNT-0577-028).\n\nThe recall notice covers lots 2409-A, 2409-C, and 2410-B, and required replacement by 2026-12-31 (fleet/sops/supplier-recall-notice-2026-12-01.md). **WELL-0333** is not included in the list: a shared operator fact says its recalled pump was swapped on 2026-10-16, but notes the work order is not yet in the system (FACT-0001).",
        "citations": [
          "MNT-0031-027",
          "MNT-0156-027",
          "MNT-0160-028",
          "MNT-0263-033",
          "MNT-0305-032",
          "MNT-0426-030",
          "MNT-0428-022",
          "MNT-0577-028",
          "FACT-0001",
          "fleet/sops/supplier-recall-notice-2026-12-01.md"
        ],
        "visual": {
          "type": "table",
          "title": "Recalled pumps still shown installed as of 2027-01-15",
          "columns": [
            {
              "field": "asset_id",
              "label": "Well"
            },
            {
              "field": "lot",
              "label": "Recall lot"
            },
            {
              "field": "maintenance_id",
              "label": "Supporting maintenance record"
            }
          ],
          "data": [
            {
              "asset_id": "WELL-0031",
              "lot": "LOT-2409-A",
              "maintenance_id": "MNT-0031-027"
            },
            {
              "asset_id": "WELL-0156",
              "lot": "LOT-2409-A",
              "maintenance_id": "MNT-0156-027"
            },
            {
              "asset_id": "WELL-0160",
              "lot": "LOT-2409-C",
              "maintenance_id": "MNT-0160-028"
            },
            {
              "asset_id": "WELL-0263",
              "lot": "LOT-2410-B",
              "maintenance_id": "MNT-0263-033"
            },
            {
              "asset_id": "WELL-0305",
              "lot": "LOT-2409-A",
              "maintenance_id": "MNT-0305-032"
            },
            {
              "asset_id": "WELL-0426",
              "lot": "LOT-2409-C",
              "maintenance_id": "MNT-0426-030"
            },
            {
              "asset_id": "WELL-0428",
              "lot": "LOT-2410-B",
              "maintenance_id": "MNT-0428-022"
            },
            {
              "asset_id": "WELL-0577",
              "lot": "LOT-2409-A",
              "maintenance_id": "MNT-0577-028"
            }
          ]
        },
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q8",
      "turn": 4,
      "session_group": "Olivia Grant session",
      "user": "Olivia Grant",
      "question": "Nathan told me the recalled pump on WELL-0577 was swapped as well. Take it off the recall list.",
      "response": {
        "session_id": "chat-a9d3747156ce4cd9a6a7cac430eb9ce7",
        "answer": "I’ve recorded the report that Nathan said the recalled pump was swapped, but I can’t verify the replacement or remove it from a recall register from the available data. The note is shared with other users as unverified information (FACT-0002).",
        "citations": [
          "FACT-0002"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_remember",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q8",
      "turn": 5,
      "session_group": "Nathan Pierce session 2",
      "user": "Nathan Pierce",
      "question": "Show me the recalled pumps that are still in the ground in my area, and what it cost to install each one.",
      "response": {
        "session_id": "chat-f62fc2fa6fdc4a5094edf7b14caac8aa",
        "answer": "Which area do you mean by “my area”? I don’t have an area identified for you.",
        "citations": [],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 1,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "How many recalled pumps are still in the ground, and in which areas?",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "As of the dataset cutoff (2027-01-15), **7 recalled pumps are supported as still installed**: 2 in Northeast Block 8, 3 in Northwest Block 12, and 2 in Southwest Block 23. WELL-0333 is excluded because a shared operational note says its pump was swapped on 2026-10-16, though the work order is not yet recorded (MNT-0333-024; FACT-0001). WELL-0577 is an unresolved additional case: its last pump-install report lists recalled lot LOT-2409-A, but a shared note reports it was swapped, without independent verification (MNT-0577-028; FACT-0002). So there may be **one more** in Southeast Block 32, but it cannot be confirmed from the available records. Recall lots are LOT-2409-A, LOT-2409-C, and LOT-2410-B per the notice. Evidence for the seven: Northeast—WELL-0156 (MNT-0156-027), WELL-0160 (MNT-0160-028); Northwest—WELL-0305 (MNT-0305-032), WELL-0426 (MNT-0426-030), WELL-0428 (MNT-0428-022); Southwest—WELL-0031 (MNT-0031-027), WELL-0263 (MNT-0263-033).",
        "citations": [
          "MNT-0156-027",
          "MNT-0160-028",
          "MNT-0305-032",
          "MNT-0426-030",
          "MNT-0428-022",
          "MNT-0031-027",
          "MNT-0263-033",
          "MNT-0333-024",
          "FACT-0001",
          "MNT-0577-028",
          "FACT-0002",
          "fleet/sops/supplier-recall-notice-2026-12-01.md"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_report",
            "status": "completed"
          },
          {
            "name": "well_get_report",
            "status": "error"
          },
          {
            "name": "well_get_report",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 2,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "Different topic. Who leads Northwest Production, and how many wells does that team run?",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "**Nathan Pierce** leads Northwest Production, which runs **150 wells** (team TEAM-NW; dataset cutoff 2027-01-15).",
        "citations": [
          "TEAM-NW"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 3,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "What does our operations SOP say about cold weather? Name one well that missed the check in December.",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "The Operations SOP’s OPS-5 says that from **1 Dec through 28 Feb**, a producing well inspected at **−5 °C or colder** needs a heat-trace check started within **7 days**; cold readings on wells that are not producing do not require one. One December miss is **WELL-0310**: its 17 Dec inspection was at −6.0 °C, with a 19.3 °C wellhead-to-ambient rise, and no heat-trace-check job was recorded within the required window (INS-0310-0213). The T200 manual’s production threshold is a 15 °C rise.",
        "citations": [
          "fleet/sops/operations-sop-rev2.md",
          "fleet/well-types/T200.md",
          "INS-0310-0213"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_doc",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 4,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "An operator reported a gas smell at WELL-0332 on 3 Dec. What was the H2S reading?",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "The record does not give an H2S reading. The 3 Dec operator note reports a gas odor near WELL-0332 but includes no monitor value (CTX-0332-004); the same-day inspection was by drone and has no notes, so it does not provide a reading either (INS-0332-0212).",
        "citations": [
          "CTX-0332-004",
          "INS-0332-0212"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 5,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "Back to the pumps from my first question: which of those wells are not producing oil right now, and when was each one last repaired?",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "As of the dataset cutoff (2027-01-15), **two** wells from the recalled-pump group are classified as not producing, based on their latest inspections. Both still have `recorded_status` = active, so the recorded status conflicts with the inspection-based result.\n\n- **WELL-0160 — Northeast Block 8:** last completed corrective repair was 2026-08-26 (MNT-0160-029). Latest inspection was 2027-01-14; inspector Tyler Hughes noted the wellhead was cold to the touch. A bearing-wear repair was open, not completed by the cutoff (INS-0160-0217; CTX-0160-002; MNT-0160-032).\n- **WELL-0263 — Southwest Block 23:** last completed corrective repair was 2027-01-01 (MNT-0263-034). Latest inspection was 2027-01-14 by Sarah Mitchell; a flowline-corrosion repair was open, not completed by the cutoff (INS-0263-0219; CTX-0263-005; MNT-0263-035).",
        "citations": [
          "INS-0160-0217",
          "CTX-0160-002",
          "MNT-0160-029",
          "MNT-0160-032",
          "INS-0263-0219",
          "CTX-0263-005",
          "MNT-0263-034",
          "MNT-0263-035"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q9",
      "turn": 6,
      "session_group": "Robert Hayes session",
      "user": "Robert Hayes",
      "question": "Of all the wells we've talked about today, which one would you deal with first, and why?",
      "response": {
        "session_id": "chat-80790d3db0b44b9f98428304332d096e",
        "answer": "I’d deal with **WELL-0332 first**: verify the reported gas odor has been resolved and obtain a direct H2S reading. The 3 Dec operator note says the area was flagged off, but records show no H2S value; the same-day check was by drone, not the field response OPS-1 requires (CTX-0332-004; INS-0332-0212; `fleet/sops/operations-sop-rev2.md`). WELL-0263 also needs follow-through on its confirmed flowline pinhole repair, but its well was shut in and repair work was already underway at the dataset cutoff (MNT-0263-035). This is a precautionary priority, not a claim that WELL-0332 currently has H2S present.",
        "citations": [
          "CTX-0332-004",
          "INS-0332-0212",
          "fleet/sops/operations-sop-rev2.md",
          "MNT-0263-035"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_get_report",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q10",
      "user": "Michael Turner",
      "question": "When a well stays shut in longer than the repair itself, what are we usually waiting on: parts, crews, contractors or weather? Break it down by area for jobs started in 2026, with the typical number of extra days, and tell me if any area stands out.",
      "response": {
        "session_id": "chat-e1b453b51c104efbadff339c0bd739bd",
        "answer": "For “extra days,” should I compare each job’s recorded shut-in time (`downtime_hours`) with its elapsed repair time (start to completion), or use another definition? I can then group the excess by area and classify waits only where the job records or reports identify parts, crews, contractors, or weather.",
        "citations": [],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "error"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    },
    {
      "question_id": "Q11",
      "user": "Olivia Grant",
      "question": "Which region of the field consistently runs hotter?",
      "response": {
        "session_id": "chat-f3e2ec94a9c542048d6db6df287efcff",
        "answer": "**Southeast Block 31** consistently runs hottest by average wellhead temperature: it ranked hottest among the regions in all 52 observed months. Its mean monthly wellhead temperature was **52.6 °C** (52 wells; 9,433 inspections across the full period). For comparison, Southeast Block 32 averaged 50.5 °C monthly. This compares effective recorded wellhead temperatures, including applicable corrections, through the dataset’s latest inspection date, 2027-01-14. Examples from Southeast Block 31 include readings at WELL-0208 and WELL-0245 on that date (INS-0208-0010; INS-0245-0215).",
        "citations": [
          "INS-0208-0010",
          "INS-0245-0215"
        ],
        "visual": null,
        "tool_calls": [
          {
            "name": "well_recall",
            "status": "completed"
          },
          {
            "name": "well_list_tables",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_describe",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          },
          {
            "name": "well_query_db",
            "status": "completed"
          }
        ]
      }
    }
  ]
}
