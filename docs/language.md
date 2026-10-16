# Language checks

Use ASD-STE100 Issue 9 as the writing standard. The local tool performs partial checks. It does not certify compliance.

The tool uses a 20-word limit for procedure sentences and a 25-word limit for other sentences. It reports selected vocabulary issues and possible passive forms. The grammar checks can produce false reports.

Code blocks, inline code, and source quotations keep their original text. A note summary must use STE.

## Local references

Put the standard and dictionary paths in `.brain/config.json`:

```json
{
  "standard": "/local/path/ASD-STE100_ISSUE9.pdf",
  "dictionary": "/local/path/ste-dictionary.json"
}
```

These paths stay on the local machine. Do not add the official standard or dictionary to Git without the required rights.

The dictionary file must use this structure:

```json
{
  "issue": 9,
  "complete": false,
  "words": {
    "use": {"part_of_speech": "verb", "meaning": "Put into operation."},
    "the": {"part_of_speech": "article", "meaning": "Specified item."}
  }
}
```

The example is incomplete. Set `complete` to true only for a complete Issue 9 dictionary. The tool checks word membership. It does not confirm the part of speech or meaning in a sentence.

The report always requires a language review. A missing dictionary gives a partial coverage report.

## Technical terms

Add a technical term to `docs/glossary.md`. Supply its definition, subject, and permitted use. Do not classify an ordinary word as a technical term to bypass a vocabulary issue.
