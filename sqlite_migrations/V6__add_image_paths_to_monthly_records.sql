-- Migration: Add checkin_image_path and checkout_image_path to monthly_records

ALTER TABLE monthly_records 
ADD COLUMN checkin_image_path TEXT;

ALTER TABLE monthly_records 
ADD COLUMN checkout_image_path TEXT;