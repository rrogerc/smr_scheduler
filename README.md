# smr_scheduler
This is the repository for the code to generate the term-based schedule for the Student Medical Response Team at the University of Calgary.

If you have any suggestions, please feel free to send me an email. It's hard anticipating all the features you want as I'm not a club member and I've tried my best to design it well but I've missed something.

## How it Works

### Overview
Instead of generating a schedule every month, the program now generates a schedule for an entire **Term** at once. 

- **Fall Term:** Covers September, October, November, and December.
- **Winter Term:** Covers January, February, March, and April.

The schedule is generated manually by the leadership team using the dashboard (see below) before the start of each term.

Based on everyone's availability, it generates a single Excel sheet for the next 4 months. It aims to be as "fair" as possible, strictly targeting **2 shifts per person per week**.

### Key Features & Changes (v2.0)

#### 1. Scheduling Logic (Network Flow Optimization)
The scheduling engine has been completely rewritten using a **Network Flow (Edmonds-Karp) Algorithm**. This is a mathematically robust approach that guarantees an optimal distribution of shifts while strictly adhering to constraints. It solves the schedule in three precise phases:

1.  **Phase 1: Senior Spread:** Prioritizes placing at least one senior in every slot (where possible) by treating them as a "scarce resource" and spreading them thin.
2.  **Phase 2: Senior Depth:** Allows slots to take a second senior if available (up to the strict limit of 2).
3.  **Phase 3: Balanced Fill:** Iteratively fills the remaining spots with all members, ensuring shifts are spread as evenly as possible across the month (preventing "clumping" or uneven loading).

**Core Constraints Enforced:**
- **Strict 2-Shift Cap:** Everyone gets max 2 shifts per week. No exceptions.
- **1 Shift Per Day:** No one is assigned back-to-back shifts or multiple shifts on the same day.
- **Max 2 Seniors:** No slot ever exceeds 2 seniors.
- **Max 5 People:** Hard limit on total slot capacity.

#### 2. Enhanced Excel Output
The generated Excel sheet is now more detailed and user-friendly:
- **Shift Count Tab:** Replaced the simple list with a detailed breakdown showing total shifts and a **month-by-month count** for each person.
- **Visuals:** **Senior names** are now highlighted in **Bold Blue** directly in the calendar grid for easy identification.
- **Warnings Tab:** A dedicated tab lists any scheduling issues (e.g., if a person couldn't be assigned 2 shifts due to availability).
- **Timestamp:** Each sheet includes a "Generated On" timestamp (**in MST**) so you know exactly when the data was created.

#### 3. Dashboard UI Improvements
- **Smart Term Selection:** The dashboard now automatically selects the **closest relevant term** based on the current date (e.g., defaults to "Fall" if you visit in September).
- **Versioning:** Schedules are now timestamped in **Calgary Time (MST)** (e.g., `schedule_Fall_2025_2025-12-31-15-30.xlsx`). Generating a new schedule **does not overwrite** the old one; it creates a new version.
- **User Friendly:** Technical terms like "Personal Access Token" have been replaced with "Dashboard Password" for ease of use.

### How the form uses the data
First, what submissions does the program take in? In SMR, availability is generally assumed to be constant for the whole term based on your class schedule. To ensure we only use active members for the specific term, we filter submissions by date:

- **For the Fall Term:** The program only considers submissions made between **August 1st and November 30th**.
- **For the Winter Term:** The program only considers submissions made between **December 1st (of the previous year) and March 31st**.

If a student submits the form multiple times during this window, the program will only take the **latest** submission based on their UCID. This allows students to update their availability by simply submitting the form again before the generation deadline.

### Deterministic Solving
The Network Flow algorithm is **fully deterministic**. This means if you run the program multiple times with the exact same availability data, it will produce the **exact same schedule** every time. There is no randomness or "dice rolling" involved. This ensures consistency and reproducibility for the leadership team.

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
