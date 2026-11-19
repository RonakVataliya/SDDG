/** A small library-system requirement set for trying the flow end to end. */
export const SAMPLE_REQUIREMENTS = `FR1: The librarian shall be able to register a new member with name, email and membership type.
FR2: A member can search the catalogue by title, author or ISBN.
FR3: The librarian shall issue a book to a registered member for 14 days.
FR4: A member can reserve a book that is currently on loan.
FR5: The system shall send a reminder email to the member two days before the due date.
FR6: The librarian shall record the return of a book and calculate any late fee.
FR7: The system shall store every loan in the loan history.
FR8: The administrator can generate a monthly report of overdue loans.

NFR1: Search results should appear within 2 seconds for a catalogue of 50,000 books.`

export const SAMPLE_USER_STORIES = `As a librarian, I want to register a new member, so that they can borrow books.
As a member, I want to search the catalogue by title, author or ISBN, so that I can find books quickly.
As a librarian, I want to issue a book to a registered member, so that loans are tracked.
As an administrator, I want to view monthly overdue reports, so that library operations are monitored.`

export const TEST_SRS_PDF_TEXT = `As a student, I want to browse upcoming campus events so that I can find activities that interest me.
As a student, I want to register for an event so that my attendance can be reserved.
As an event organizer, I want to create and edit event details so that students can see accurate information.
As an event organizer, I want to view the attendee list so that I can plan event logistics.
As an administrator, I want to deactivate inappropriate event listings so that the event catalogue remains appropriate.

FR-001: The system shall allow a student to create an account using a valid university email address and password.
FR-002: The system shall allow registered users to sign in using their email address and password.
FR-003: The system shall display upcoming events with each event's title, date, time, venue, and organizer.
FR-004: The system shall allow an organizer to create an event by providing a title, description, date, start time, venue, and capacity.
FR-005: The system shall allow an organizer to update an event while its status is Draft or Published.
FR-006: The system shall allow a student to register for a published event that has available capacity.
FR-007: The system shall prevent a student from registering more than once for the same event.
FR-008: The system shall show an event's remaining capacity after a successful registration.
FR-009: The system shall allow an organizer to view and export the attendee list for an event.
FR-010: The system shall allow an administrator to deactivate an event that violates campus event policies.

NFR-001: The system shall load the event listing page within 3 seconds for 95% of requests under a load of 500 concurrent users.
NFR-002: The system shall encrypt passwords using a secure one-way password hashing algorithm.
NFR-003: The system shall use HTTPS for all client-server communication in production.
NFR-004: The system shall be available 99.5% of each calendar month, excluding scheduled maintenance.
NFR-005: The system shall support the latest two major versions of Chrome, Firefox, Safari, and Edge.`


