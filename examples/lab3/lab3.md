# Lab 3: A web server with nginx

*Linux Administration, week 3. Estimated time: 30 minutes.*

## Before you start

Log in to your lab VM as `student`. You will need `sudo`. All commands are run in a
terminal.

## Task 1: Install nginx

1. Refresh the package index with `sudo apt-get update`.
2. Install nginx: `sudo apt-get install -y nginx`.
3. Check the installed version with `nginx -v`.

## Task 2: Start the service

1. Enable and start the service in one command:
   `sudo systemctl enable --now nginx`.
2. Confirm it runs: `systemctl is-active nginx` must print `active`.

## Task 3: Publish your own page

1. Replace the default page:
   `echo '<h1>Lab 3 by student</h1>' | sudo tee /var/www/html/index.html`.
2. Fetch it with `curl -s http://localhost`. You should see your heading.

*(page 2)*

## Task 4: Check the configuration and the log

1. Test the configuration with `sudo nginx -t`. It must say *syntax is ok*.
2. Request a page that does not exist: `curl -sI http://localhost/missing`. Note the
   status code (404).
3. Look at the last two lines of the access log:
   `sudo tail -n 2 /var/log/nginx/access.log`. Both of your requests are there.

## Task 5: Clean up

Stop the service with `sudo systemctl stop nginx` and check that
`systemctl is-active nginx` now prints `inactive`.

## Hand-in

A screenshot of Task 4, step 3.
