#!/bin/bash

# Verification Script for Whaleray Database Feature
# Usage: ./test_db_flow.sh <API_URL> <AUTH_TOKEN>

API_URL=$1
AUTH_TOKEN=$2

if [ -z "$API_URL" ] || [ -z "$AUTH_TOKEN" ]; then
  echo "Usage: ./test_db_flow.sh <API_URL> <AUTH_TOKEN>"
  exit 1
fi

echo "1. Creating Database..."
CREATE_RES=$(curl -s -X POST "$API_URL/db/createdb" \
  -H "Authorization: $AUTH_TOKEN")
echo "Response: $CREATE_RES"

DB_ID=$(echo $CREATE_RES | jq -r '.databaseId')

if [ "$DB_ID" == "null" ]; then
  echo "Failed to create database"
  exit 1
fi

echo "Database ID: $DB_ID"

echo "2. Getting Database Info..."
sleep 2
GET_RES=$(curl -s -X GET "$API_URL/db" \
  -H "Authorization: $AUTH_TOKEN")
echo "Response: $GET_RES"

echo "3. Resetting Password..."
RESET_RES=$(curl -s -X POST "$API_URL/db/reset-password" \
  -H "Authorization: $AUTH_TOKEN")
echo "Response: $RESET_RES"

echo "4. Deleting Database..."
DELETE_RES=$(curl -s -X DELETE "$API_URL/db" \
  -H "Authorization: $AUTH_TOKEN")
echo "Response: $DELETE_RES"
