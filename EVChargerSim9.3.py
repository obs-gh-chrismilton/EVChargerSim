import requests
from datetime import datetime
import random
import json
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
log_handler = RotatingFileHandler('charging_sessions.log', maxBytes=10*1024*1024, backupCount=5)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_handler.setFormatter(log_formatter)

logging.basicConfig(
    handlers=[log_handler],
    level=logging.DEBUG
)

try:
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)
        logging.info("Configuration loaded successfully.")
    with open('cities.json', 'r') as cities_file:
        cities_info = json.load(cities_file)
        logging.info("Cities information loaded successfully.")
    with open('chargers.json', 'r') as chargers_file:
        chargers_by_city = json.load(chargers_file)
        logging.info("Chargers by city loaded successfully.")
except Exception as e:
    logging.error(f"Error loading files: {e}")
    exit(1)

def is_peak_hour(timestamp):
    peak_hours = config['simulation']['peak_hours']
    result = peak_hours[0] <= timestamp.hour <= peak_hours[1] or peak_hours[2] <= timestamp.hour <= peak_hours[3]
    logging.debug(f"Checking peak hour for timestamp {timestamp}: {result}")
    return result

def get_city_population(city_name):
    for city in cities_info:
        if city['name'] == city_name:
            population = city.get('population', 0)
            logging.debug(f"City {city_name} population: {population}")
            return population
    logging.warning(f"Population for city {city_name} not found.")
    return 0

def adjust_probabilities_for_population(population):
    if population < 1000000:
        probabilities = [0.3, 0.2, 0.4, 0.1]
    elif population < 3000000:
        probabilities = [0.4, 0.15, 0.35, 0.1]
    else:
        probabilities = [0.5, 0.1, 0.3, 0.1]
    logging.debug(f"Probabilities adjusted for population {population}: {probabilities}")
    return probabilities

def simulate_charger_state(city_name):
    population = get_city_population(city_name)
    probabilities = adjust_probabilities_for_population(population)
    state = random.choices(['In Use', 'Maintenance', 'Idle', 'Interruption'], weights=probabilities, k=1)[0]
    logging.info(f"Simulated state for {city_name}: {state}")
    return state

def get_state_duration(state):
    if state in ['In Use', 'Interruption']:
        duration = random.randint(5, 10)
    elif state == 'Maintenance':
        duration = random.randint(1, 3)
    else:
        duration = random.randint(1, 2)
    logging.debug(f"State duration for {state}: {duration} minutes")
    return duration

def generate_random_userID():
    userID = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
    logging.debug(f"Generated random userID: {userID}")
    return userID

def get_in_use_message(percentage_complete):
    messages = [
        "Charging session initiated successfully. Current draw is within expected parameters.",
        "User has commenced charging. Charger is now active and delivering power.",
        "Charging in progress. Vehicle is accepting charge at optimal rate.",
        "Charging session midway. Battery charging efficiency is at peak performance.",
        "Charging nearing completion. Preparing for session termination and payment processing."
    ]
    index = int(min(len(messages) - 1, percentage_complete // 20))
    message = messages[index]
    logging.debug(f"In-use message selected: {message}")
    return message

def get_maintenance_message():
    message = random.choice([
        "Charger offline for scheduled maintenance. Expected downtime is 30 minutes.",
        "Maintenance mode activated due to reported malfunction. Technician has been notified.",
        "Undergoing emergency maintenance for hardware issue. Apologies for the inconvenience.",
        "Maintenance update: Replacement of faulty components underway. Charger soon to be operational.",
        "Final checks post-maintenance indicating all systems go. Charger returning to service shortly."
    ])
    logging.debug(f"Maintenance message selected: {message}")
    return message

def get_interruption_message():
    message = random.choice([
        "Interruption due to power fluctuation detected. Attempting to resume charging.",
        "Emergency stop triggered by user. Assessing charger status before resuming.",
        "Unforeseen interruption encountered. Charger performing self-diagnostic.",
        "Interruption due to network connectivity issue. Re-establishing connection.",
        "Power surge detected. Charger temporarily offline to safeguard vehicle and charger integrity."
    ])
    logging.debug(f"Interruption message selected: {message}")
    return message

def generate_session_for_charger(charger, city_name):
    state_name, country = None, None
    for city in cities_info:
        if city['name'] == city_name:
            state_name = city['state']
            country = city['country']
            break

    state = simulate_charger_state(city_name)
    userID, message, vehicle_type, estimated_charging_time = None, "", None, 0

    if state == 'In Use':
        userID = generate_random_userID()
        vehicle_type = random.choice(['Sedan', 'SUV', 'Truck', 'Motorcycle'])
        estimated_charging_time = get_state_duration(state)
        message = get_in_use_message(0)
    else:
        userID = None
        vehicle_type = None  # Ensure this is explicitly set to None when not 'In Use'
        estimated_charging_time = get_state_duration(state)
        if state == 'Maintenance':
            message = get_maintenance_message()
        elif state == 'Interruption':
            message = get_interruption_message()
        else:  # Handle 'Idle' or other states if necessary
            message = "Charger is currently idle."

    session = {
        'sessionID': str(uuid.uuid4()),
        'userID': userID,
        'charger_id': charger['charger_id'],
        'start_time': datetime.now(),
        'status': state,
        'initial_status': state,  # Add this line to store the initial state
        'city_name': city_name,
        'state_name': state_name,
        'country': country,
        'latitude': charger.get('latitude', 0.0),
        'longitude': charger.get('longitude', 0.0),
        'charging_duration': estimated_charging_time,
        'percentage_complete': 0,
        'powerOutput': None if state != 'In Use' else 0.0,
        'end_time': None,
        'message': message,
        'vehicle_type': vehicle_type,
        'estimated_charging_time': estimated_charging_time,
        'actual_charging_time': 0,
        'interruptions': 0,
    }
    logging.info(f"Generated session: {session}")
    return session

def should_generate_session(current_time):
    result = is_peak_hour(current_time) or random.choice([True, False])
    logging.debug(f"Decision to generate session: {result}")
    return result

def update_sessions(active_sessions):
    updated_sessions = []
    current_time = datetime.now()
    for session in active_sessions:
        elapsed_time_seconds = (current_time - session['start_time']).total_seconds()
        session_duration_seconds = max(1, session['charging_duration'] * 60)  # Ensure not zero

        session['percentage_complete'] = min(100, (elapsed_time_seconds / session_duration_seconds) * 100)

        if session['status'] == 'In Use' and session['percentage_complete'] < 100:
            session['powerOutput'] = (session['percentage_complete'] / 100) * random.uniform(5.0, 20.0)

        if session['status'] == 'Interruption':
            if random.random() < 0.5:  # Chance to resolve interruption
                logging.info(f"Resolving interruption for session {session['sessionID']}.")
                session['status'] = 'In Use'
                session['message'] = get_in_use_message(session['percentage_complete'])

        if session['percentage_complete'] >= 100:
            logging.info(f"Marking session {session['sessionID']} as completed. Percentage complete: {session['percentage_complete']}")
            initial_status = session['initial_status']
            logging.info(f"Session {session['sessionID']} was initially a {initial_status} session.")

            # Continue with 'Completed' updates:
            session['status'] = 'Completed'
            session['initial_status'] = initial_status
            session['message'] = "Session completed successfully."
            session['end_time'] = current_time
            session['actual_charging_time'] = elapsed_time_seconds / 60
            session['total_power_output'] = session['powerOutput']  # Store the final powerOutput value

            # Transmit Data AFTER modifying the session:
            send_data(session)

        else:
            logging.debug(f"Session {session['sessionID']} not yet completed. Percentage complete: {session['percentage_complete']}.")
            updated_sessions.append(session)  # Add to updated sessions if not 'Completed'

    return updated_sessions


def send_data(session):
    logging.debug(f"Preparing to send data for sessionID {session['sessionID']} with status {session['status']} and completion {session['percentage_complete']}%.")
    if session['status'] in ['In Use', 'Maintenance', 'Interruption', 'Idle', 'Completed']:
        session_for_json = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in session.items()}
        headers = {'Authorization': f"Bearer {config['auth_token']}", 'Content-Type': 'application/json'}
        try:
            if session['status'] == 'Completed':
                if session_for_json['total_power_output'] is not None:
                    session_for_json['message'] = f"Session completed successfully. Total power output: {session_for_json['total_power_output']:.2f} kWh."
                else:
                    session_for_json['message'] = "Session completed successfully. No power output recorded."
            response = requests.post(config['api_endpoint'], json=session_for_json, headers=headers)
            if response.status_code == 200:
                logging.info(f"Data sent successfully for sessionID {session['sessionID']} with status {session['status']}.")
            else:
                logging.warning(f"Failed to send data for sessionID {session['sessionID']}: {response.text}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error sending data for sessionID {session['sessionID']}: {e}")

def generate_sessions_based_on_conditions(active_sessions, chargers_by_city):
    new_sessions = []
    current_time = datetime.now()
    for city_name, chargers in chargers_by_city.items():
        if should_generate_session(current_time):
            for charger in chargers:
                has_active_session = any(session['charger_id'] == charger['charger_id'] 
                         and session['status'] in ['In Use', 'Interruption', 'Maintenance'] 
                         for session in active_sessions) 

                if not has_active_session:
                    new_session = generate_session_for_charger(charger, city_name)
                    new_sessions.append(new_session)
                    logging.info(f"New session generated for charger {charger['charger_id']} in {city_name} with status {new_session['status']}.")
    return new_sessions

if __name__ == "__main__":
    active_sessions = []
    logging.info("Script started...")
    while True:
        time.sleep(config['simulation']['session_timing']['update_interval'])
        new_sessions = generate_sessions_based_on_conditions(active_sessions, chargers_by_city)
        active_sessions.extend(new_sessions)
        active_sessions = update_sessions(active_sessions)
        for session in active_sessions:
            send_data(session)
