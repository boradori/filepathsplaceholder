# File Paths Placeholder
The File Paths Placeholder is a dynamic desktop application designed to streamline the management and execution of file-related commands. Built with PyQt5, this app offers an intuitive graphical user interface (GUI) facilitating the organization, modification, and execution of file paths and URLs.

## Key Features:
- **File List Widget**: Store file paths, URLs, or any text string in the File List Widget.
	- **Space bar**: "Quick Look" feature for macOS.
	- **Enter**: Edit item text
	- **Double click**: Launch
	- **Use "➕" button**: The File List Widget can store file paths, URLs, or any text string after entering `:}`.
		- `:}` allows its following text string to be stored in the File List Widget. Otherwise, the widget rejects to save the entered text string.
	- **Drag-and-Drop Functionality**: Drag and drop files into and out of the File List Widget to copy files.
		- **Files**: Drag and drop files to the File List Widget from a folder. Drag and drop files to another folder, text editor, etc. from the File List Widget.
		- **URLs**: Drag and drop URLs to the File List Widget from the web browsers. Drag and drop an URL to the web browser.
		- Easily rearrange file paths and URLs within the widget using the built-in drag-and-drop feature, enhancing user interaction and efficiency.
- **Expand**: Expand the app window to access the side widgets.
- **Left List Widget** (the left of the File List Widget): Store commands on the left hand side of the File List Widget.
	- **Store commands**: Store commands such as `python`, `python -m`, `node`, `open`, `sleep`, `yt-dl...` etc.
- **Play List Widget**:
	- **Command Execution**: Execute commands based on the file paths or URLs listed, by clicking on "▶" button. 
	- **Run All Commands**: Click on the large "▶" button to execute every command one at a time (from top to bottom).
- **Right List Widget** (the right of the File List Widget): Store commands on the right hand side of the File List Widget.
	- **Store commands**: Store commands that come after file paths or URL.
	- Any text string that comes after `:}` in this widget is ignored. Use it as `comment`.
- **List Management**: Import and export lists of file paths, URLs, or commands as CSV files, making it easy to save progress and share lists between sessions or with other users.
- **Font Size Adjustment**: Customize the app's appearance by adjusting the font size, ensuring accessibility and personal preference accommodation. Use `Cmd +` and `Cmd -` .
- **Refresh**: Click on the "🔄" button to see if any file path no longer exists.

## Getting Started:
To use the File Paths Placeholder App, clone the repository to your local machine and ensure you have Python and PyQt5 installed. Follow the instructions in the README for setting up and launching the app.

This app is perfect for users seeking an efficient way to manage a variety of file paths and URLs, execute commands, and organize their workflow with the flexibility of a customizable GUI.
