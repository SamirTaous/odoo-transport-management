# Transport Management for Odoo 16

![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)
![Odoo Version: 16.0](https://img.shields.io/badge/Odoo-16.0-blueviolet.svg)

A custom Odoo module for managing transport missions effectively. This module provides the foundational structure for planning, executing, and tracking transport operations.

## Key Features

-   **Mission Creation:** Create transport missions with a unique, automatically generated reference number (e.g., `TM/00001`).
-   **Core Details:** Assign a mission date, source location, a driver (`res.partner`), and a vehicle (`fleet.vehicle`).
-   **Multi-Destination Management:** Each mission can have a list of ordered destinations, allowing for complex route planning.
-   **Status Workflow:** Track the mission's progress through a clear lifecycle using a status bar:
    -   `Draft` -> `Confirmed` -> `In Progress` -> `Done`
    -   With options to `Cancel` and `Reset to Draft`.
-   **Integrated Communication:** A full chatter is available on each mission form for logging notes, sending messages to followers, and tracking field changes.

## Models

This module introduces two new models to the Odoo database:

### 1. Transport Mission (`transport.mission`)

This is the main model that represents a single transport job.
-   `name`: The unique reference (e.g., TM/00001).
-   `mission_date`: The date of the mission.
-   `driver_id`: A many-to-one link to a Partner (Driver).
-   `vehicle_id`: A many-to-one link to a Vehicle.
-   `destination_ids`: A one-to-many link to the `transport.destination` model.
-   `state`: The current status of the mission.

### 2. Transport Destination (`transport.destination`)

This model holds the details for each stop in a mission.
-   `mission_id`: A many-to-one link back to the parent mission.
-   `location`: A text field for the destination address or point.
-   `sequence`: An integer to define the order of the stops.

## Technical Details

-   **Dependencies:** This module depends on the following official Odoo apps:
    -   `base`: The core Odoo framework.
    -   `fleet`: For vehicle management (`fleet.vehicle` model).
    -   `mail`: For the chatter and activity features (`mail.thread` and `mail.activity.mixin`).
-   **Sequencing:** It uses an `ir.sequence` record to automatically generate mission reference numbers upon creation.

## Installation

1.  Place this module's folder (or a symbolic link to it) inside your Odoo `custom_addons` directory.
2.  Restart the Odoo server service.
3.  In the Odoo UI, navigate to the **Apps** menu.
4.  Click **Update Apps List** (Developer Mode may need to be activated).
5.  Search for "Transport Management" and click **Install**.

## Usage

1.  After installation, a new top-level menu item named **Transport** will appear in the main Odoo menu.
2.  Click on **Transport** -> **Missions** to view the list of all transport missions.
3.  Click the **New** button to open the form and create a new mission.

## Future Development (Planned Features)

-   [ ] Calculate total distance for a mission.
-   [ ] Manage and track mission-related costs (fuel, tolls, etc.).
-   [ ] Generate and print a "Mission Work Order" PDF report.
-   [ ] Integration with Odoo's Calendar app to show driver schedules.
-   [ ] A dashboard for mission analytics (missions per month, costs vs. time, etc.).

---

**Author:** Samir Taous
