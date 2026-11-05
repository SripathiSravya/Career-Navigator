# Career Navigator

A Flask application that analyses a user's profile and PDF resume, recommends careers from its expandable local career database, identifies skill gaps, evaluates resume quality and job readiness, and provides a learning roadmap and example job roles.

## Added features
- **Job Description Skill Matcher:** paste a job description and compare detected technical skills with the user's entered skills.
- **Project Recommendation System:** receive beginner, intermediate, and advanced project ideas for a selected career, including skills to practise and expected outcomes.

Career Trend Analysis has been removed. The application does not require external API keys. Job-description matching is keyword-based and detects skills currently listed in the career database; it does not evaluate proficiency or guarantee a hiring outcome.

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run `python -m pip install -r requirements.txt`.
4. Run `python app.py`.
5. Open `http://127.0.0.1:5000/`.

The SQLite database is created automatically on first run. Resume upload accepts PDF files up to 5 MB.

## Deploy
Start command: `gunicorn app:app`


## Dashboard navigation update
After submitting a profile, use the left sidebar to open the available career-analysis features individually. The desktop workspace keeps the sidebar fixed and scrolls the selected content area independently.


## Career database updates

- **ESCO occupation import:** checks the ESCO occupation source at application startup and then every 24 hours while the Flask process remains running. A saved timestamp prevents another check until 24 hours have elapsed.
- **Job-market discovery:** checks the Himalayas public remote-jobs API for India-eligible listings at application startup and then every 24 hours.
- New career titles are imported only when the available source data contains enough matching technical-skill evidence from the skills already known to the local career database. Duplicate career names are skipped.
- ESCO is a European occupation and skills classification, not a live Indian vacancy feed. The importer currently requests a limited page of ESCO results; it does not guarantee coverage of every ESCO occupation or every newly emerging career.
- The Himalayas feed is a remote-jobs source and is not a complete Indian job-market crawler. It may miss onsite Indian vacancies and roles not represented in the feed.
- A daily check means the application checks for available source updates every 24 hours; it does not mean either source publishes new careers every day.
- The periodic scheduler runs inside the Flask application process. On hosting platforms, it runs only while that process is alive. Multiple web workers or instances can cause duplicate scheduler processes; database uniqueness and saved timestamps reduce duplicate imports, but a dedicated single scheduler process is preferable for larger deployments.
