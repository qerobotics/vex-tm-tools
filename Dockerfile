# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container to match the compose file volume mount
WORKDIR /srv/vtmt

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# Define the command to run the application when the container starts
CMD ["python", "main.py"]
