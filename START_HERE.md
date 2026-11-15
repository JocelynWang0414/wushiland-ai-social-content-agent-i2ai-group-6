# Start the interactive application

1. Extract the entire ZIP archive.
2. On Windows, double-click `START_APP.cmd`. Python 3.10+ is required. If timezone data is missing, run `python -m pip install tzdata`.
3. The browser should open automatically. Otherwise, copy the localhost URL printed in the terminal. Keep the terminal running while using the app.
4. Expand **API connections**, enter your Gemini key, and select **Connect for this session**. Bright Data is required only for online collection. The original development environment can load its locally encrypted Bright Data key; that file is not included in this package.
5. Choose a data source:
   - **My uploaded video data**: expand **Data sources**, download the CSV column template, enter real video records, upload the file, and select **Use this file**. TikTok and Instagram Reel records are supported.
   - **Online TikTok discovery**: connect Bright Data and use keyword-based video discovery.
6. Choose the first day of your planning week and click **Generate weekly recommendations**. Upload mode reads your file only. Online mode reuses data collected within 24 hours or collects new data when necessary.
7. If an online collection is waiting, the same button resumes the saved collection. Clicking again while a job is running returns to its progress page instead of submitting another collection.

Keys entered through the app remain in server memory. Reconnect Gemini after restarting. This ZIP excludes credentials, active jobs, uploaded files and new raw collection outputs.

## Planning dates and evidence dates

Choosing November 11 plans November 11-17. If today is November 13, suggested posts will not be scheduled on November 11 or 12. Current metrics cannot reconstruct what was known at the start of the week.

The app accepts weeks containing today or future dates. Fully past weeks require historical snapshots and a separate replay workflow. Uploaded files retain their original observation dates; uploading does not make old evidence current.

## Collection limits and progress

Online discovery searches three broad queries, with up to six records per query. Complete discovery records are reused; otherwise, up to 18 video-detail inputs may be requested. Collection and Gemini analysis consume their respective account quotas.

Failures are displayed explicitly. Old data is not presented as a successful new collection. A remote collection may continue after the local polling timeout; resume the saved collection rather than submitting another one blindly.

## Other platforms and Colab

From this extracted directory, run `python -m wushiland.app`. The app uses the Python standard library plus timezone data where required. For Colab, adapt your existing port-display setup to use `wushiland.app.Handler` and assign `Application()` to `server.app`. The legacy README's repository-cloning example fetches the GitHub branch, not these unmerged local changes.

## Verification

The current version passed 46 offline/mock tests, including HTTP upload and CSRF checks, source validation, date handling, model-output validation and confirmation that upload analysis never invokes Bright Data. The latest changes have not been verified with a new live Gemini call. See `TP2_CHANGES.md` for scope and limitations.
