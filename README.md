# smr_scheduler
This is the repository for the code to generate the term-based schedule for the Student Medical Response Team at the University of Calgary.

If you have any suggestions, please feel free to send me an email. It's hard anticipating all the features you want as I'm not a club member and I've tried my best to design it well but I've missed something.

## How it Works

### Overview
Instead of generating a schedule every month, the program now generates a schedule for an entire **Term** at once. 

- **Fall Term:** Covers September, October, November, and December.
- **Winter Term:** Covers January, February, March, and April.

The schedule is generated manually by the leadership team using the dashboard (see below) before the start of each term.

Based on everyone's availability, it generates a single Excel sheet for the next 4 months. It aims to be as "fair" as possible, strictly targeting **2 shifts per person per month**.

### Key Features & Changes (v2.0)

#### 1. Scheduling Logic (Fairness & Constraints)
The algorithm has been overhauled to prioritize fairness and specific club constraints:
- **Strict 2-Shift Cap:** The system enforces a **strict maximum of 2 shifts per person per month**. It will **never** automatically assign a 3rd shift to anyone, even if slots remain empty.
- **Under-Assignment:** If a member has limited availability and cannot be assigned 2 shifts, the system will assign what it can and list them in the **Warnings** tab. It is up to leadership to manually resolve these gaps.
- **Slot Capacity:** Each time slot (e.g., 8AM-10AM) can hold up to **5 people**.
- **Senior Constraints:** 
    - Every slot aims to have **at least 1 senior**.
    - No slot will ever have **more than 2 seniors**.
    - If no senior is available (or all available seniors have reached their 2-shift cap), the slot may remain without a senior, and a warning will be logged.
- **Distribution:** Shifts are distributed intelligently to maximize coverage (i.e., slots with 0 people get filled before adding a 3rd person to another slot).

#### 2. Enhanced Excel Output
The generated Excel sheet is now more detailed and user-friendly:
- **Shift Count Tab:** Replaced the simple list with a detailed breakdown showing total shifts and a **month-by-month count** for each person.
- **Visuals:** **Senior names** are now highlighted in **Bold Blue** directly in the calendar grid for easy identification.
- **Warnings Tab:** A dedicated tab lists any scheduling issues (e.g., if a person couldn't be assigned 2 shifts due to availability).
- **Timestamp:** Each sheet includes a "Generated On" timestamp so you know exactly when the data was created.

#### 3. Dashboard UI Improvements
- **Global Term Selector:** A clear selector at the top controls both the view and the generator.
- **Versioning:** Schedules are now timestamped (e.g., `schedule_Fall_2025_2025-12-31...`). Generating a new schedule **does not overwrite** the old one; it creates a new version.
- **User Friendly:** Technical terms like "Personal Access Token" have been replaced with "Dashboard Password" for ease of use.

### How the form uses the data
First, what submissions does the program take in? In SMR, availability is generally assumed to be constant for the whole term based on your class schedule. To ensure we only use active members for the specific term, we filter submissions by date:

- **For the Fall Term:** The program only considers submissions made between **August 1st and November 30th**.
- **For the Winter Term:** The program only considers submissions made between **December 1st (of the previous year) and March 31st**.

If a student submits the form multiple times during this window, the program will only take the **latest** submission based on their UCID. This allows students to update their availability by simply submitting the form again before the generation deadline.

### Tie-Breaking
If multiple people are vying for a time spot and they both have the same number of shifts that week, the tie-breaker is handled via a **deterministic hash**. This means the selection appears random but is consistent—if you run the program again with the same data, the same person will get the spot.

### Calendar Integration
I've included in the output a ICS integration. The user just needs to click on the link in the spreadsheet and they can subscribe to it in their calendar app. This way, if any changes are made to the schedule their calendar will also be updated automatically.

## Dashboard (The UI)
I've built a simple UI hosted on GitHub Pages so leaders can manually trigger a schedule generation.

To use the dashboard:
1. Log in with your **Dashboard Password** (GitHub Token).
2. Choose the **Term** and **Year** from the global selector.
3. Click **Generate New Version**.
4. The new Excel file will appear in the list once the GitHub Action finishes (usually takes ~30 seconds).

## Security
This repository needs to be public in order to do calendar integration. Because of this, I've hidden sensitive information like the Excel Sheet link and email keys using GitHub Secrets. I've also setup a hash for the ICS calendar links so the links for each person are random and have no identifying data.
