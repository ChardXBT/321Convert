# File Converter Project [321Convert]

## Description

A web-based file conversion tool that allows users to convert between different document and image formats with ease.

**Live Demo:** [321Convert](https://three21convert.onrender.com)

## Features

- Convert images between multiple formats
- Convert documents between multiple formats
- Simple and intuitive web interface
- Fast and efficient conversion process
- No need for installation accessible from the web

## Installation

### Prerequisites

- Python 3.8+
- pip (Python package manager)

### Setup

1. **Clone the repository**

   ```sh
   git clone https://github.com/YOUR-USERNAME/File_Converter.git
   cd File_Converter
   ```

2. **Create a virtual environment**

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**

   ```sh
   pip install -r requirements.txt
   ```

4. **Run the application**

   ```sh
   python app.py
   ```

5. **Access the application**
   Open your web browser and go to `http://127.0.0.1:5000/`

## Technologies Used
- **Flask**: Web framework for Python, used for handling requests and routing.
- **Pillow**: Image processing library, used for image conversions and transformations.
- **pdf2docx**: Library for converting PDFs to DOCX format.
- **pandas**: Data analysis and manipulation library, especially for Excel and CSV file handling.
- **Tesseract OCR**: Optical Character Recognition tool for extracting text from images.
- **HTML/CSS**: For designing and structuring the frontend of the web application.
- **Flask-CORS**: Handles Cross-Origin Resource Sharing (CORS) to allow secure communication between the frontend and backend.
- **gunicorn**: WSGI HTTP server for deploying the Flask app in a production environment.
- **python-docx**: Library for creating, modifying, and converting DOCX files.
- **docx2pdf**: Converts DOCX files to PDFs.
- **docxcompose**: Python library for merging and composing DOCX documents.
- **pypdf**: For working with PDF files, including reading and extracting text.
- **python-dotenv**: Loads environment variables from a `.env` file for configuration.
- **openpyxl**: Library for reading and writing Excel (XLSX) files.
- **xhtml2pdf**: Converts HTML to PDF.

## Future Improvements
- Currently none


## Contributions

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a new branch (`git checkout -b feature-branch`)
3. Commit your changes (`git commit -m "Add new feature"`)
4. Push to the branch (`git push origin feature-branch`)
5. Open a pull request

For major changes, please open an issue first to discuss what you'd like to change.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Developed with ❤️ by Chardium**

