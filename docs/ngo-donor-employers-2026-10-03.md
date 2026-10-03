# Development agencies, foundations and INGOs in BiH (checked 2026-10-03)

Question: do these ten employers have, or did they recently have, openings in
Bosnia and Herzegovina for BiH nationals? These are outside the original
missions/IGO scope (see BACKLOG), so no sources were enabled. Recruitment
channels were checked live; historical evidence comes mainly from
[mreza-mira.net](https://www.mreza-mira.net/), the local board where these
offices advertise national staff.

Several URLs in the original list no longer work: giz.de/en/jobs.html, the KAS
`bosnien-und-herzegowina/jobs` page, iri.org/work-with-us/careers and the old
JICA careers URL return 404; fes.ba and savethechildren.taleo.net do not resolve.

| Employer | Open in BiH now | Past BiH national hiring (evidence) | Recruitment channel | Integration |
| --- | --- | --- | --- | --- |
| GIZ | None found | Yes, regularly: Local Intern (deadline 29.12.2025), Technical Advisor (Feb 2025), Communication Specialist (Nov 2024), internship (Jan 2025). Expert roles posted in 2022 were international. | Local hiring by GIZ Office Sarajevo on mreza-mira.net/local boards. The global portal jobs.giz.de loads results through JavaScript. | No usable official listing. Local postings would need a mreza-mira source (third-party board). |
| Konrad-Adenauer-Stiftung | None | No staff postings found; only annual scholarships (2025/26, 2026/27). | Central openings at kas.de/de/offene-stellen are Germany-based (interamt.de). | Not worth a source. |
| Friedrich-Ebert-Stiftung | None | No staff postings found. | bosnia-and-herzegovina.fes.de: rolling internships of 2–3 months, applications by email, German and BHS required. | No listing to scrape. |
| NDI | None (1 global opening, Washington) | Offices in Sarajevo and Banja Luka; no BiH postings found. | Rippling `ndi_careers` (public JSON API) and a UKG board (0 openings). | Possible: Rippling API includes country. Not needed now. |
| IRI | None (7 openings, all Washington DC) | Resident Program Director in Sarajevo historically; no recent local postings found. | UKG/UltiPro INT1048 job, consulting and internship boards (public JSON). | Possible with a UKG adapter. Low yield. |
| JICA | None: Balkan Office page says "Currently we have no vacancy" | Balkan Office is in Sarajevo (Bistrik 9). | jica.go.jp …/balkan/others/employment.html | Could use `generic` with that "no vacancy" text as `empty_text`. Low yield. |
| TIKA | None found | No public postings found. | No careers channel; Sarajevo office contact only. | Not possible. |
| Catholic Relief Services | None (35 open jobs worldwide, none in Europe) | A "CRS BiH Project Assistant" (refugee integration project) was posted on mreza-mira; the post has since been removed, so its date is unverified. | Oracle Candidate Experience `eipn.fa.us2…/sites/CX_1` | **Ready**: the existing `oracle` adapter runs cleanly (0 BiH jobs). |
| Save the Children | None (73 open jobs worldwide, 0 in BiH) | Yes, national-only roles in 2026: Cultural Mediator for Arabic, Sarajevo Canton (26.6.–5.7.2026); Director of Impact and Partnerships, Sarajevo preferred (7.–16.4.2026). | Oracle Candidate Experience `hcri.fa.em2…/sites/CX_1`; the NWB jobs page returns 403. | **Ready**: the existing `oracle` adapter runs cleanly (0 BiH jobs). |
| SDC (Swiss cooperation) | None new. The page still lists Political Advisor (2025). | SDC hires in BiH through the Swiss Embassy (Political Advisor 2025, project coordinator calls). | eda.admin.ch Sarajevo vacancies page | **Already covered** by the enabled `swiss` source. |

## Recommendation

- If the employer scope widens to INGOs, add Save the Children and CRS first.
  Neither needs new code: use `oracle` with `allow_empty`. Save the Children
  advertised two national BiH roles in 2026.
- GIZ is the largest local employer here, but it advertises BiH national posts on
  local boards rather than in a scrapable official listing.
- KAS, FES, TIKA and JICA rarely or never post local vacancies publicly.

## Related coverage gap found

unjobs.org's Sarajevo list shows UNDP individual-consultant notices (for example
"GEF8-Flora Expert on invasive alien species", "SPA-Expert for … Wildfire
Preparedness", "5NC-GHG Data Consolidation Expert", Sept 2026). These are open to
BiH nationals but are absent from our UNDP Oracle source because UNDP publishes
them on its procurement-notices system.
