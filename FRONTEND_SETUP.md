# Frontend Setup Instructions

## Overview
This document provides a complete guide to setting up the frontend for the PDF Manager application.

## Prerequisites
- Node.js (v14 or later)
- npm (Node Package Manager)

Make sure you have Node.js and npm installed by running:

```bash
node -v
npm -v
```

## Setup Instructions

### For Command Prompt (CMD)
1. **Clone the Repository**  
   Open CMD and clone the repository:
   ```bash
   git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
   ```

2. **Navigate to the Project Directory**  
   ```bash
   cd PDF-Manager
   ```

3. **Install Dependencies**  
   Install the necessary packages:
   ```bash
   npm install
   ```

4. **Start the Development Server**  
   Launch the application:
   ```bash
   npm start
   ```

5. **Access the Application**  
   Open your browser and navigate to `http://localhost:3000`

### For PowerShell
1. **Clone the Repository**  
   Open PowerShell and clone the repository:
   ```powershell
   git clone https://github.com/rahulmisra2010-ctrl/PDF-Manager.git
   ```

2. **Navigate to the Project Directory**  
   ```powershell
   cd PDF-Manager
   ```

3. **Install Dependencies**  
   Install the necessary packages:
   ```powershell
   npm install
   ```

4. **Start the Development Server**  
   Launch the application:
   ```powershell
   npm start
   ```

5. **Access the Application**  
   Open your browser and navigate to `http://localhost:3000`

## Troubleshooting Guide
- **If you encounter an error related to npm not being recognized:**  
  Ensure Node.js and npm are installed correctly. Close and reopen CMD/PowerShell to refresh the environment variables.

- **If the application does not start:**  
  Make sure there are no errors during `npm install`. Check for port conflicts.

- **Common Errors:**  
  - *Error: ENOENT*: This usually indicates that the folder does not exist. Ensure that you are in the correct directory.
  - *Error: EACCES*: This indicates permission issues. Try running CMD/PowerShell as an administrator.  

## Conclusion
You have now set up the frontend for the PDF Manager application. If you encounter further issues, please refer to the official documentation or community forums.