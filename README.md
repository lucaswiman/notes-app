# Notes CLI

## Configuration

* Install python 3.10 and Poetry.
* Set `NOTES_PATH` environment variable to the path where you want to store notes,
  e.g. `~/dropbox/notes` or whatever.
* Set `NOTES_TEMPLATE_PATH` environment variable if you want to use custom templates.
  You may find better results forking the repository and editing it to your needs.
  There is no stable API.
* Set an alias for running the notes command.

Put all that in your ~/.bash_profile file. Mine looks like this:
```bash
export NOTES_PATH='/Users/lucaswiman/personal/notes-data'
function note () (
  cd /Users/lucaswiman/personal/notes-app
  poetry run python -m notes.note $@
)
```

## Usage

There are a few kinds of templates:
* due-date - a note with a due date. I use this for tasks assigned to me by others.
* event - A note about a thing that happened, e.g. starting a new diet or medication.
  * TODO: add interface for querying events.
* note - Catchall markdown document. There is a yaml section at the end for storing structured data.
* prediction - A record of a time estimate. Includes an estimate with range or standard deviation.
  This shows up as a task without a due date.
* task - A thing that needs doing, optionally by some date.
* metric (TODO: finish implementing this.)

To add an item, run `note record <type>`.

To see a list of items, run `note list <type>`. You can add `--edit` to pick a file to edit.


Each list includes a "file id" which is a hash of the file name. It can be used to edit the file,
e.g. `note edit c24898a208`. Tasks can be completed (or notes marked as irrelevant) by running 
`note complete <file id>`.

Most templates define an `irrelevant_after` field, which is a date after which the note is no
longer relevant. This will keep your TODO list clean if there's something you feel too guilty to
remove manually. You may also choose `never` to never mark an item as irrelevant.

Time formats can be in business days, a particular date, a number of days or hours, etc.

To mark a task/prediction/etc. as complete, run `note complete <file id>`.

## Installation

This repo is intended to be fitted to my personal needs. If you find anything useful here, I would
recommend forking the repo and configuring it however you like. I may at some point deploy this to
pypi for convenience in installing it on multiple computers, but I have no intention of supporting
it for other users.