# smr_scheduler
This is the repository for the code to generate the term-based schedule for the Student Medical Response Team at the University of Calgary.

If you have any suggestions, please feel free to send me an email. It's hard anticipating all the features you want as I'm not a club member and I've tried my best to design it well but I've missed something.

## How it Works

### Overview
Instead of generating a schedule every month, the program now generates a schedule for an entire **Term** at once. 

- **Fall Term:** Covers September, October, November, and December.
- **Winter Term:** Covers January, February, March, and April.

The program runs automatically twice a year:
1. **August 25th at 12:00am MST:** Generates the Fall schedule.
2. **December 25th at 12:00am MST:** Generates the Winter schedule.

Based on everyone's availability, it generates a single Excel sheet for the next 4 months. It aims to be as "fair" as possible, meaning that it aims for everyone to have roughly the same amount of shifts over the course of the term.

Because of this, I have included statistics. Inside the excel sheet there is a "Person Schedule" tab that contains the number of shifts everyone is working. In addition, there is also a "Log" tab and individual tabs for each month (e.g., "September 2025", "October 2025").

### How the form uses the data
First, what submissions does the program take in? In SMR, availability is generally assumed to be constant for the whole term based on your class schedule. To ensure we only use active members for the specific term, we filter submissions by date:

- **For the Fall Term:** The program only considers submissions made between **August 1st and November 30th**.
- **For the Winter Term:** The program only considers submissions made between **December 1st (of the previous year) and March 31st**.

If a student submits the form multiple times during this window, the program will only take the **latest** submission based on their UCID. This allows students to update their availability by simply submitting the form again before the generation deadline.

### Scheduling Algorithm
The program tries to be as fair as possible, as I described in the overview. There is also an issue of tiebreakers: if multiple people are vying for a time spot and they both have the same number of shifts that week, then how do you tie break? 

I've decided to do it both randomly and deterministically. Basically, instead of using something unfair like alphabetical to tie-break, I've decided to create a hash. This means that whoever gets the time slot is random, but if you run the program again the same person will be chosen, hence the determinism.

### Calendar Integration
I've included in the output a ICS integration. The user just needs to click on the link in the spreadsheet and they can subscribe to it in their calendar app. This way, if any changes are made to the schedule their calendar will also be updated automatically.

## Dashboard (The UI)
I've built a simple UI hosted on GitHub Pages so leaders can manually trigger a schedule generation if needed (e.g., if you need to remake the schedule in the middle of a term).

To use the dashboard:
1. Log in with a **GitHub Personal Access Token** (ask Roger for this if you don't have it).
2. Choose the **Term** and **Year**.
3. Click **Run Generator**.
4. The new Excel file will appear in the list once the GitHub Action finishes (usually takes 1-2 minutes).

## Security
This repository needs to be public in order to do calendar integration. Because of this, I've hidden sensitive information like the Excel Sheet link and email keys using GitHub Secrets. I've also setup a hash for the ICS calendar links so the links for each person are random and have no identifying data.