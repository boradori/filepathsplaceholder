import subprocess, shlex, sys, platform, os, csv, threading, contextlib, queue
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (QApplication, QWidget, QListWidget, QVBoxLayout, QPushButton,
                             QShortcut, QHBoxLayout, QFileDialog, QMessageBox, QListWidgetItem,
                             QInputDialog, QLabel)
from PyQt5.QtCore import Qt, QMimeData, QUrl, QEvent, QItemSelectionModel
from PyQt5.QtGui import QDrag, QKeySequence, QFont

# Define filenames for the current list and font size
CURRENT_LIST_FILENAME = "current_list.csv"
FONT_SIZE_FILENAME = "font_size.csv"

# Context manager for subprocess management
@contextlib.contextmanager
def managed_subprocess(*args, **kwargs):
    process = subprocess.Popen(*args, **kwargs)
    try:
        yield process
    finally:
        if process.poll() is None:  # If the process is still running
            process.terminate()
            process.wait()


class DraggableListWidget(QListWidget):
    def __init__(self, currentFontSize):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.currentFontSize = currentFontSize
        self.setFont(QFont("Arial", self.currentFontSize))
        self.applyListStyle()

    def applyListStyle(self):
        self.setFont(QFont("Arial", self.currentFontSize))
        itemHeight = 22
        self.setStyleSheet("""
            QListWidget::item {
                border-bottom: 1px solid #dcdcdc;  /* Line separator */
                padding: 4px;                     /* Add some padding */
                height: {itemHeight}px;          /* Fixed item height */
            }
            QListWidget::item:selected {
                background-color: #5DADE2;   /* Background color for selected item */
                color: black;                /* Text color for selected item */
            }
        """)

    def connectScroll(self, otherWidgets):
        def syncScroll(value):
            for widget in otherWidgets:
                if widget.verticalScrollBar() is not self.verticalScrollBar():
                    widget.verticalScrollBar().setValue(value)
        self.verticalScrollBar().valueChanged.connect(syncScroll)

    def mousePressEvent(self, event):
        if not self.itemAt(event.pos()):
            self.clearSelection()
            self.parent().clearAllSelectionsExcept(self)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            # Handle copy event
            selectedItems = self.selectedItems()
            if len(selectedItems) == 1:
                clipboard = QApplication.clipboard()
                clipboard.setText(selectedItems[0].text())
        elif event.matches(QKeySequence.Paste):
            # Handle paste event for URLs
            self.pasteClipboardContent()
        elif platform.system() == 'Darwin' and event.key() == Qt.Key_Space:
            # Existing Quick Look feature for macOS
            self.quickLookSelectedFile()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # Handle Enter key for editing text
            selectedItem = self.currentItem()
            if selectedItem:
                self.editItemText(selectedItem)
        elif event.key() == Qt.Key_Left and self.parent().leftListWidget.isVisible():
            self.parent().leftListWidget.setFocus()
            self.parent().leftListWidget.setCurrentRow(self.currentRow())
            self.parent().leftListWidget.setCurrentItem(self.parent().leftListWidget.currentItem(), QItemSelectionModel.Select)
        elif event.key() == Qt.Key_Right and self.parent().rightListWidget.isVisible():
            self.parent().rightListWidget.setFocus()
            self.parent().rightListWidget.setCurrentRow(self.currentRow())
            self.parent().rightListWidget.setCurrentItem(self.parent().rightListWidget.currentItem(), QItemSelectionModel.Select)
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Additional handling for Delete and Backspace keys
            if self == self.parent().fileListWidget:
                self.parent().deleteSelectedItems()
            else:
                for item in self.selectedItems():
                    item.setText('')
                if self == self.parent().leftListWidget:
                    self.parent().updatePlayListWidget()
        else:
            super(DraggableListWidget, self).keyPressEvent(event)

    def quickLookSelectedFile(self):
        # Assuming self.parent() is the instance of FilePathsPlaceholder
        # which contains fileListWidget
        selectedItems = self.parent().fileListWidget.selectedItems()
        if not selectedItems:
            return  # Exit the method if no item is selected in fileListWidget

        selectedItem = self.currentItem()
        if selectedItem:
            filePath = selectedItem.text()
            # subprocess.run(["qlmanage", "-p", filePath], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            threading.Thread(target=lambda: subprocess.run(["qlmanage", "-p", filePath], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT), daemon=True).start()

            # Do not consume the event, allowing arrow keys to work for list navigation
            return False

    def editItemText(self, item):
        # Create a QInputDialog instance
        inputDialog = QInputDialog(self)
        inputDialog.setWindowTitle("Edit Item")
        inputDialog.setLabelText("Enter text:")
        inputDialog.setTextValue(item.text())

        # Set a fixed size for the dialog
        inputDialog.resize(400, 200)  # You can adjust these values as needed

        # Execute the dialog and check the result
        ok = inputDialog.exec_()
        text = inputDialog.textValue()

        if ok:
            # Check if the entered text is not just whitespace
            newText = text if text.strip() else ""
            item.setText(newText)

    def pasteClipboardContent(self):
        clipboard = QApplication.clipboard()
        clipboard_text = clipboard.text()
        if clipboard_text:
            # Check if the clipboard text is a valid URL
            parsed_url = QUrl(clipboard_text)
            is_valid_url = parsed_url.isValid() and (parsed_url.scheme().startswith('http') or parsed_url.scheme().startswith('https'))

            # Check if the clipboard text is an existing file path
            is_existing_file = os.path.exists(clipboard_text)

            # Replace text of selected items if clipboard content is valid
            if is_valid_url or is_existing_file:
                for selectedItem in self.selectedItems():
                    selectedItem.setText(clipboard_text)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.setDropAction(Qt.MoveAction if event.source() == self else Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        # Handle internal moves
        if event.source() == self:
            super(DraggableListWidget, self).dropEvent(event)

        # Handle external drops
        elif event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                # Add file or URL to fileListWidget
                self.addItem(QListWidgetItem(url.toLocalFile() if url.isLocalFile() else url.toString()))

            # Call addEmptySideListItems and updatePlayListWidget after adding items
            self.parent().addEmptySideListItems()
            event.accept()

    def startDrag(self, supportedActions):
        drag = QDrag(self)
        mimeData = QMimeData()

        # Initialize an empty list for URLs
        urls = []
        text_list = []

        for item in self.selectedItems():
            item_text = item.text()
            parsed_url = QUrl(item_text)
            
            # Check if the item's text is a valid URL
            if parsed_url.isValid() and parsed_url.scheme():
                # Append to URL list for recognized URL
                urls.append(parsed_url)
                # Also add to text list for compatibility
                text_list.append(item_text)
            else:
                # Handle as a local file path
                urls.append(QUrl.fromLocalFile(item_text))

        # Set both URLs and plain text to the MIME data
        mimeData.setUrls(urls)
        mimeData.setText('\n'.join(text_list))
        drag.setMimeData(mimeData)
        drag.exec_(Qt.CopyAction)
        

class FilePathsPlaceholder(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('File Paths Placeholder')
        self.resize(500, 600)
        self.executor = ThreadPoolExecutor(max_workers=2)  # For managing subprocesses
        self.setupUI()
        self.stopAllCommands = False  # Flag to control stopping of all commands
        self.commandQueue = queue.Queue()
        self.commandThread = threading.Thread(target=self.processCommandQueue)
        self.commandThread.daemon = True
        self.commandThread.start()

    def setupUI(self):
        self.createFilePPFolder()
        self.currentFontSize = self.loadFontSize()
        self.setupListWidgets()
        self.setupButtons()
        self.setupLayout()
        self.loadLastUsedList()
        self.leftListWidget.installEventFilter(self)
        self.rightListWidget.installEventFilter(self)
        QApplication.instance().aboutToQuit.connect(self.saveLastUsedListPath)

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress:
            if source in [self.leftListWidget, self.rightListWidget]:
                if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                    # Clear text for selected items in leftListWidget or rightListWidget
                    for item in source.selectedItems():
                        item.setText('')
                    if source == self.leftListWidget:
                        self.updatePlayListWidget()
                    return True
                elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                    # Handle Enter key for editing text
                    selectedItem = source.currentItem()
                    if selectedItem:
                        self.editItemText(selectedItem)
                    return True
        return super(FilePathsPlaceholder, self).eventFilter(source, event)

    def createFilePPFolder(self):
        self.filepp_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'FilePP')
        os.makedirs(self.filepp_folder, exist_ok=True)
        self.current_list_file = os.path.join(self.filepp_folder, CURRENT_LIST_FILENAME)
        self.font_size_file = os.path.join(self.filepp_folder, FONT_SIZE_FILENAME)

    def applyListStyle(self, listWidget):
        listWidget.setFont(QFont("Arial", self.currentFontSize))
        itemHeight = 22  # Set this to your desired default item height
        listWidget.setStyleSheet(f"""
            QListWidget::item {{
                border-bottom: 1px solid #dcdcdc;  /* Line separator */
                padding: 4px;                     /* Add some padding */
                height: {itemHeight}px;          /* Fixed item height */
            }}
            QListWidget::item:selected {{
                background-color: #5DADE2;       /* Background color for selected item */
                color: black;                    /* Text color for selected item */
            }}
        """)

    def setupListWidgets(self):
        self.fileListWidget = DraggableListWidget(self.currentFontSize)
        self.fileListWidget.setMinimumWidth(400)
        self.applyListStyle(self.fileListWidget)
        self.fileListWidget.itemDoubleClicked.connect(self.executeFilePath)
        self.fileListWidget.itemSelectionChanged.connect(lambda: self.clearOtherSelections(self.fileListWidget))

        self.playListWidget = PlayListWidget()
        self.playListWidget.setFixedWidth(60)
        self.applyListStyle(self.playListWidget)
        self.playListWidget.hide()
        self.playListWidget.itemClicked.connect(self.onPlayButtonClick)
        self.playListWidget.itemSelectionChanged.connect(lambda: self.clearOtherSelections(self.playListWidget))

        self.leftListWidget = LeftListWidget()
        self.leftListWidget.setMinimumWidth(200)
        self.leftListWidget.hide()
        self.applyListStyle(self.leftListWidget)
        self.leftListWidget.itemDoubleClicked.connect(self.editItemText)
        self.leftListWidget.itemSelectionChanged.connect(lambda: self.clearOtherSelections(self.leftListWidget))

        self.rightListWidget = RightListWidget()
        self.rightListWidget.setMinimumWidth(260)
        self.rightListWidget.hide()
        self.applyListStyle(self.rightListWidget)
        self.rightListWidget.itemDoubleClicked.connect(self.editItemText)
        self.rightListWidget.itemSelectionChanged.connect(lambda: self.clearOtherSelections(self.rightListWidget))

        # Connect their scrolls
        allWidgets = [self.playListWidget, self.leftListWidget, self.fileListWidget, self.rightListWidget]
        for widget in allWidgets:
            widget.connectScroll(allWidgets)

    def setupButtons(self):
        self.expandButton = QPushButton('↔️')
        self.expandButton.setFixedSize(50, 50)
        self.expandButton.setFont(QFont("Arial", 24))
        self.expandButton.clicked.connect(self.expandListWidgets)
        self.exportButton = QPushButton('💾')
        self.exportButton.setFixedSize(50, 50)
        self.exportButton.setFont(QFont("Arial", 24))
        self.exportButton.clicked.connect(self.exportList)
        self.importButton = QPushButton('📂')
        self.importButton.setFixedSize(50, 50)
        self.importButton.setFont(QFont("Arial", 24))
        self.importButton.clicked.connect(self.importList)
        self.refreshButton = QPushButton('🔄')
        self.refreshButton.setFixedSize(50, 50)
        self.refreshButton.setFont(QFont("Arial", 24))
        self.refreshButton.clicked.connect(self.refreshList)
        self.addButton = QPushButton('➕')
        self.addButton.setFixedSize(50, 50)
        self.addButton.setFont(QFont("Arial", 24))
        self.addButton.clicked.connect(self.addNewItem)

        # New button for running all "▶" items
        self.runAllButton = QPushButton("▶")
        self.runAllButton.setFixedSize(50, 50)
        self.runAllButton.setFont(QFont("Arial", 24))
        self.runAllButton.clicked.connect(self.runAllPlayItems)
        self.runAllButton.setDisabled(True)

        self.increaseFontShortcut = QShortcut(QKeySequence("Ctrl+="), self)
        self.decreaseFontShortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        self.increaseFontShortcut.activated.connect(lambda: self.changeFontSize(True))
        self.decreaseFontShortcut.activated.connect(lambda: self.changeFontSize(False))

    def setupLayout(self):
        listLayout = QHBoxLayout()
        listLayout.addWidget(self.playListWidget, 1)
        listLayout.addWidget(self.leftListWidget, 1)
        listLayout.addWidget(self.fileListWidget, 2)
        listLayout.addWidget(self.rightListWidget, 1)

        buttonLayout = QHBoxLayout()
        for button in [self.runAllButton, self.expandButton, self.exportButton, self.importButton, self.refreshButton, self.addButton]:
            buttonLayout.addWidget(button)

        mainLayout = QVBoxLayout()
        mainLayout.addLayout(listLayout)
        mainLayout.addLayout(buttonLayout)
        self.setLayout(mainLayout)

    def clearAllSelectionsExcept(self, listWidget):
        for lw in [self.playListWidget, self.fileListWidget, self.leftListWidget, self.rightListWidget]:
            if lw is not listWidget:
                lw.clearSelection()

    def clearOtherSelections(self, selectedListWidget):
        for listWidget in [self.playListWidget, self.fileListWidget, self.leftListWidget, self.rightListWidget]:
            if listWidget is not selectedListWidget:
                listWidget.clearSelection()
                
    def deleteSelectedItems(self):
        selectedRows = sorted([self.fileListWidget.row(item) for item in self.fileListWidget.selectedItems()], reverse=True)
        for row in selectedRows:
            self.fileListWidget.takeItem(row)
            # Also delete corresponding items in leftListWidget and rightListWidget
            if row < self.leftListWidget.count():
                self.leftListWidget.takeItem(row)
            if row < self.rightListWidget.count():
                self.rightListWidget.takeItem(row)
            # Additionally, remove the corresponding play button in playListWidget
            if row < self.playListWidget.count():
                self.playListWidget.takeItem(row)

    def addNewItem(self):
        text, ok = QInputDialog.getText(self, 'Add New Item', 'Enter file path, URL, or :} item:')
        if ok and text:
            is_special_item = text.startswith(':}')
            is_valid_path_or_url = os.path.exists(text) or urlparse(text).scheme in ('http', 'https')
            if is_special_item or is_valid_path_or_url:
                self.fileListWidget.addItem(text)
                self.leftListWidget.addItem(QListWidgetItem(""))  # Consistency across lists
                self.rightListWidget.addItem(QListWidgetItem(""))
                self.updatePlayListWidget()
            else:
                QMessageBox.warning(self, "Invalid Input", "Please enter a valid file path, URL, or :} item.")

    def updatePlayListWidget(self):
        currentScrollPos = self.playListWidget.verticalScrollBar().value()

        # Check if update is necessary: either count differs or items are out of sync
        update_needed = self.playListWidget.count() != self.leftListWidget.count()
        if not update_needed:
            for i in range(self.leftListWidget.count()):
                leftItemText = self.leftListWidget.item(i).text()
                playItemWidget = self.playListWidget.itemWidget(self.playListWidget.item(i))
                playItemText = playItemWidget.text() if playItemWidget else ""
                if (leftItemText and playItemText != "▶") or (not leftItemText and playItemText):
                    update_needed = True
                    break

        if update_needed:
            self.playListWidget.clear()
            for i in range(self.leftListWidget.count()):
                itemText = self.leftListWidget.item(i).text()
                if itemText:
                    playItem = QListWidgetItem(self.playListWidget)
                    playLabel = QLabel("▶")
                    playLabel.setAlignment(Qt.AlignCenter)
                    playLabel.setFont(QFont("Arial", 14))
                    # Adjust these values as needed to match the item height in other lists
                    # playLabel.setMinimumHeight(20)
                    # playLabel.setMaximumHeight(24)
                    self.playListWidget.setItemWidget(playItem, playLabel)
                else:
                    self.playListWidget.addItem(QListWidgetItem(""))

        self.playListWidget.verticalScrollBar().setValue(currentScrollPos)

    def onPlayButtonClick(self, item):
        row = self.playListWidget.currentRow()
        if row != -1 and self.fileListWidget.item(row) and self.fileListWidget.item(row).text().strip():
            self.disableInteraction()
            command = self.constructCommandForRow(row)

            # Execute the command in a separate thread
            self.commandThread = threading.Thread(target=lambda: self.runCommand(command))
            self.commandThread.start()

    # def runCommand(self, command):
    #     self.runningProcess = subprocess.Popen(command, shell=True)
    #     self.runningProcess.wait()  # Wait for the process to complete
    #     self.enableInteraction()    # Re-enable interaction after completion
        
    def runCommand(self, command):
        # Disable interaction if needed before starting the command
        self.disableInteraction()
        self.runningProcess = None  # Initialize runningProcess
        self.commandThread = threading.Thread(target=lambda: self.executeCommand(command))
        self.commandThread.start()

    def executeCommand(self, command):
        try:
            # Execute the command and handle output
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.runningProcess = process  # Track the running process

            # Read output line by line
            for line in process.stdout:
                print(line.strip())
                if self.runningProcess is None:
                    break  # Stop if runningProcess is cleared

            if self.runningProcess:
                _, errors = process.communicate()
                if errors:
                    print(f"Errors: {errors.strip()}")

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            self.runningProcess = None
            self.enableInteraction()
            self.playListWidget.setFocus()  # Set focus back to playListWidget

    def disableInteraction(self):
        # Disable main interaction parts, not the entire GUI
        self.fileListWidget.setDisabled(True)
        self.leftListWidget.setDisabled(True)
        self.rightListWidget.setDisabled(True)
        self.playListWidget.setDisabled(True)

    def enableInteraction(self):
        # Re-enable the previously disabled elements
        self.fileListWidget.setDisabled(False)
        self.leftListWidget.setDisabled(False)
        self.rightListWidget.setDisabled(False)
        self.playListWidget.setDisabled(False)

    def selectAllItems(self, listWidget):
        listWidget.selectAll()

    def addEmptySideListItems(self):
        while self.leftListWidget.count() < self.fileListWidget.count():
            self.leftListWidget.addItem(QListWidgetItem(""))
        while self.rightListWidget.count() < self.fileListWidget.count():
            self.rightListWidget.addItem(QListWidgetItem(""))
        while self.playListWidget.count() < self.fileListWidget.count():
            self.playListWidget.addItem(QListWidgetItem(""))

    def changeFontSize(self, increase):
        newFontSize = self.currentFontSize + 1 if increase and self.currentFontSize < 30 else self.currentFontSize - 1 if not increase and self.currentFontSize > 12 else self.currentFontSize
        if newFontSize != self.currentFontSize:
            self.currentFontSize = newFontSize
            for listWidget in [self.playListWidget, self.fileListWidget, self.leftListWidget, self.rightListWidget]:  # Include playListWidget
                self.applyListStyle(listWidget)

    def editItemText(self, item):
        # Create a QInputDialog instance
        inputDialog = QInputDialog(self)
        inputDialog.setWindowTitle("Edit Item")
        inputDialog.setLabelText("Enter text:")
        inputDialog.setTextValue(item.text())

        # Set a fixed size for the dialog
        inputDialog.resize(400, 200)  # You can adjust these values as needed

        # Execute the dialog and check the result
        ok = inputDialog.exec_()
        text = inputDialog.textValue()

        if ok:
            # Check if the entered text is not just whitespace
            newText = text if text.strip() else ""
            item.setText(newText)
            self.updatePlayListWidget()

    def expandListWidgets(self):
        # Toggle visibility of the additional QListWidgets
        self.leftListWidget.setVisible(not self.leftListWidget.isVisible())
        self.rightListWidget.setVisible(not self.rightListWidget.isVisible())
        self.playListWidget.setVisible(not self.playListWidget.isVisible())

        # Toggle enabled state of the new button
        self.runAllButton.setEnabled(self.playListWidget.isVisible())

        # Update playListWidget to sync with leftListWidget if it's being made visible
        if self.playListWidget.isVisible():
            self.updatePlayListWidget()

    def runAllPlayItems(self):
        # Check if there is at least one "▶" item in playListWidget
        has_playable_item = any(
            self.playListWidget.itemWidget(self.playListWidget.item(row)) and 
            self.playListWidget.itemWidget(self.playListWidget.item(row)).text() == "▶" 
            for row in range(self.playListWidget.count())
        )

        if not has_playable_item:
            QMessageBox.warning(self, "No runnable commands", "There are no commands to run.")
            return

        self.disableInteraction()  # Disable interaction at the start
        self.stopAllCommands = False  # Reset the stop flag before starting

        def run_command(row):
            if self.stopAllCommands:  # Check if stopping is requested before running the command
                return
            if row < self.playListWidget.count():
                playItemWidget = self.playListWidget.itemWidget(self.playListWidget.item(row))
                if playItemWidget and playItemWidget.text() == "▶":
                    command = self.constructCommandForRow(row)
                    self.executeCommand(command)
                    if self.stopAllCommands:  # Check if stopping is requested after running the command
                        return

        # Running the commands in a separate thread
        self.commandThread = threading.Thread(target=lambda: [run_command(row) for row in range(self.playListWidget.count())])
        self.commandThread.start()

    def constructCommandForRow(self, row):
        leftItemText = self.leftListWidget.item(row).text() if self.leftListWidget.item(row) else ""
        filePath = self.fileListWidget.item(row).text() if self.fileListWidget.item(row) else ""
        rightItemText = self.rightListWidget.item(row).text() if self.rightListWidget.item(row) else ""

        # Special handling for ':}' in filePath
        if filePath.startswith(':}'):
            filePath = filePath[2:].lstrip()

        # Splitting rightItemText at ':}' if present
        rightItemText = rightItemText.split(':}')[0]

        # Constructing the command based on the platform
        command = f'{leftItemText} "{filePath}" {rightItemText}' if platform.system() == 'Windows' else f'{leftItemText} {shlex.quote(filePath)} {rightItemText}'

        return command
    
    def processCommandQueue(self):
        while True:
            command = self.commandQueue.get()
            if command:
                self.executeCommand(command)
            self.commandQueue.task_done()

    def loadFontSize(self):
        default_font_size = 12
        try:
            if os.path.exists(self.font_size_file):
                with open(self.font_size_file, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.reader(file)
                    for row in reader:
                        return int(row[0]) if row else default_font_size
            else:
                return default_font_size
        except Exception as e:
            print(f"Error loading font size: {e}")
            return default_font_size

    def saveFontSize(self):
        with open(self.font_size_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([self.currentFontSize])  # Save the current font size

    def closeEvent(self, event):
        self.saveFontSize()  # Save the font size before closing
        self.executor.shutdown(wait=False)
        super().closeEvent(event)

    def clearList(self):
        self.playListWidget.clear()
        self.leftListWidget.clear()
        self.fileListWidget.clear()
        self.rightListWidget.clear()

    def isValidPathOrUrl(self, text):
        parsed_url = urlparse(text)
        return parsed_url.scheme and parsed_url.netloc or os.path.exists(text)

    def refreshList(self):
        indexesToRemove = []
        for index in range(self.fileListWidget.count()):
            item_text = self.fileListWidget.item(index).text()
            if item_text.startswith(':}') or self.isValidPathOrUrl(item_text):
                continue
            indexesToRemove.append(index)

        # Removing items in reverse order to avoid index shifting issues
        for index in sorted(indexesToRemove, reverse=True):
            self.fileListWidget.takeItem(index)
            if index < self.leftListWidget.count():
                self.leftListWidget.takeItem(index)
            if index < self.rightListWidget.count():
                self.rightListWidget.takeItem(index)
            if index < self.playListWidget.count():
                self.playListWidget.takeItem(index)

        # Optionally update the saved list if changes were made
        if indexesToRemove:
            self.saveLastUsedListPath()

    def saveLastUsedListPath(self):
        with open(self.current_list_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["LeftItem", "FilePath", "RightItem"])  # Write headers

            maxItems = max(self.fileListWidget.count(), self.leftListWidget.count(), self.rightListWidget.count())
            for i in range(maxItems):
                leftItem = self.leftListWidget.item(i).text() if i < self.leftListWidget.count() else ""
                rightItem = self.rightListWidget.item(i).text() if i < self.rightListWidget.count() else ""
                filePath = self.fileListWidget.item(i).text() if i < self.fileListWidget.count() else ""
                writer.writerow([leftItem, filePath, rightItem])
    
    def loadLastUsedList(self):
        if os.path.exists(self.current_list_file):
            with open(self.current_list_file, 'r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader, None)  # Skip headers

                self.playListWidget.clear()
                self.leftListWidget.clear()
                self.fileListWidget.clear()
                self.rightListWidget.clear()

                for leftItem, filePath, rightItem in reader:
                    self.leftListWidget.addItem(QListWidgetItem(leftItem))
                    self.rightListWidget.addItem(QListWidgetItem(rightItem))
                    
                    # Accept :} prefixed items or valid file paths/URLs
                    if filePath.startswith(':}') or self.isValidPathOrUrl(filePath):
                        self.fileListWidget.addItem(QListWidgetItem(filePath))
                    else:
                        # Optionally handle missing file paths, e.g., add a placeholder or log
                        pass

                self.updatePlayListWidget()
    
    def executeFilePath(self, item):
        filepath = item.text()
        try:
            if platform.system() == 'Windows':
                os.startfile(filepath)  # For Windows
            else:
                opener = 'open' if platform.system() == 'Darwin' else 'xdg-open'
                subprocess.call([opener, filepath])  # For macOS and Linux
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open the file: {e}")

    def cleanupAfterTermination(self):
        self.enableInteraction()         # Re-enable interaction
        if hasattr(self, 'runningProcess'):
            del self.runningProcess      # Remove the attribute

    def showErrorDialog(self, message):
        # Show error dialog in the main thread
        QApplication.instance().postEvent(self, CustomEvent(lambda: QMessageBox.critical(self, "Error", message)))

    def event(self, event):
        if isinstance(event, CustomEvent):
            event.execute()
        return super().event(event)

    def clearListSelections(self):
        self.fileListWidget.clearSelection()
        self.leftListWidget.clearSelection()
        self.rightListWidget.clearSelection()
        self.playListWidget.clearSelection()

    def terminateRunningProcess(self):
        if self.runningProcess:
            self.runningProcess.terminate()
            self.runningProcess = None
            self.enableInteraction()
            self.stopAllCommands = True  # Also stop all commands if one is terminated

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            # Check and terminate the running process
            if hasattr(self, 'runningProcess') and self.runningProcess is not None:
                self.terminateRunningProcess()

            # Check and stop all commands in the thread
            if hasattr(self, 'commandThread') and self.commandThread.is_alive():
                self.stopAllCommands = True

            # Clear selections in all list widgets
            if (not hasattr(self, 'runningProcess') or self.runningProcess is None) and \
            (not hasattr(self, 'commandThread') or not self.commandThread.is_alive()) or \
            self.stopAllCommands:
                self.clearListSelections()
        else:
            super(FilePathsPlaceholder, self).keyPressEvent(event)

    def exportList(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "CSV Files (*.csv)")
            if file_path:
                with open(file_path, 'w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerow(["LeftItem", "FilePath", "RightItem"])  # CSV headers

                    # Iterate through the lists and write rows
                    maxItems = max(self.fileListWidget.count(), self.leftListWidget.count(), self.rightListWidget.count())
                    for i in range(maxItems):
                        leftItem = self.leftListWidget.item(i).text() if i < self.leftListWidget.count() else ""
                        rightItem = self.rightListWidget.item(i).text() if i < self.rightListWidget.count() else ""
                        filePath = self.fileListWidget.item(i).text() if i < self.fileListWidget.count() else ""
                        writer.writerow([leftItem, filePath, rightItem])

                QMessageBox.information(self, "Export Successful", "The list was successfully exported.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {e}")
            
    def importList(self, file_path=None, auto_load=False):
        if not file_path and not auto_load:
            file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "CSV Files (*.csv)")
            if not file_path:  # User cancelled the file dialog
                return

        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader, None)  # Skip the header
                
                self.playListWidget.clear()
                self.leftListWidget.clear()
                self.fileListWidget.clear()
                self.rightListWidget.clear()

                for leftItem, filePath, rightItem in reader:
                    # Add items to the lists only if the file path is valid
                    if os.path.exists(filePath):
                        self.fileListWidget.addItem(QListWidgetItem(filePath))
                        self.leftListWidget.addItem(QListWidgetItem(leftItem))
                        self.rightListWidget.addItem(QListWidgetItem(rightItem))
                        # Optionally, handle invalid file paths if necessary
                        # else:
                        # # Handle missing file paths, e.g., log or notify user

                self.updatePlayListWidget()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while importing: {e}")


class PlayListWidget(QListWidget):
    def __init__(self, parent=None):
        super(PlayListWidget, self).__init__(parent)
        self.setDragDropMode(QListWidget.NoDragDrop)
        self.setSelectionMode(QListWidget.SingleSelection)  # Enable selection

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Right:
            self.parent().leftListWidget.setFocus()
            self.parent().leftListWidget.setCurrentRow(self.currentRow())
            self.parent().leftListWidget.setCurrentItem(self.parent().leftListWidget.currentItem(), QItemSelectionModel.Select)
            self.clearSelection()  # Clear selection in playListWidget
        elif event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            row = self.currentRow()
            if row != -1 and self.itemWidget(self.item(row)) and self.itemWidget(self.item(row)).text() == "▶":
                self.parent().onPlayButtonClick(self.item(row))
        else:
            super(PlayListWidget, self).keyPressEvent(event)

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if item and self.itemWidget(item) and self.itemWidget(item).text() == "▶":
            super().mousePressEvent(event)
            self.parent().clearAllSelectionsExcept(self)
        else:
            self.clearSelection()
            # Optionally, you can also clear all selections in other widgets
            self.parent().clearAllSelectionsExcept(self)

    def connectScroll(self, otherWidgets):
        def syncScroll(value):
            for widget in otherWidgets:
                if widget.verticalScrollBar() is not self.verticalScrollBar():
                    widget.verticalScrollBar().setValue(value)
        self.verticalScrollBar().valueChanged.connect(syncScroll)


class LeftListWidget(QListWidget):
    def __init__(self, parent=None):
        super(LeftListWidget, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            if clipboard_text:
                for selectedItem in self.selectedItems():
                    selectedItem.setText(clipboard_text)

                if hasattr(self.parent(), 'updatePlayListWidget'):
                    self.parent().updatePlayListWidget()
        elif event.key() == Qt.Key_Right:
            self.parent().fileListWidget.setFocus()
            self.parent().fileListWidget.setCurrentRow(self.currentRow())
            self.parent().fileListWidget.setCurrentItem(self.parent().fileListWidget.currentItem(), QItemSelectionModel.Select)
        elif event.key() == Qt.Key_Left:
            self.parent().playListWidget.setFocus()
            self.parent().playListWidget.setCurrentRow(self.currentRow())
            self.parent().playListWidget.setCurrentItem(self.parent().playListWidget.currentItem(), QItemSelectionModel.Select)
            self.clearSelection()
        else:
            super().keyPressEvent(event)
    
    def mousePressEvent(self, event):
        if not self.itemAt(event.pos()):
            self.clearSelection()
            self.parent().clearAllSelectionsExcept(self)
        super().mousePressEvent(event)

    def connectScroll(self, otherWidgets):
        def syncScroll(value):
            for widget in otherWidgets:
                if widget.verticalScrollBar() is not self.verticalScrollBar():
                    widget.verticalScrollBar().setValue(value)
        self.verticalScrollBar().valueChanged.connect(syncScroll)

    def dropEvent(self, event):
        # Call the original dropEvent to handle the internal move
        super(LeftListWidget, self).dropEvent(event)

        # Check if the source of the event is the same widget (internal move)
        if event.source() == self:
            # Call the updatePlayListWidget method on the parent
            # after the items in leftListWidget are reordered
            if hasattr(self.parent(), 'updatePlayListWidget'):
                self.parent().updatePlayListWidget()


class RightListWidget(QListWidget):
    def __init__(self, parent=None):
        super(RightListWidget, self).__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            clipboard = QApplication.clipboard()
            clipboard_text = clipboard.text()
            if clipboard_text:
                for selectedItem in self.selectedItems():
                    selectedItem.setText(clipboard_text)
        elif event.key() == Qt.Key_Left:
            self.parent().fileListWidget.setFocus()
            self.parent().fileListWidget.setCurrentRow(self.currentRow())
            self.parent().fileListWidget.setCurrentItem(self.parent().fileListWidget.currentItem(), QItemSelectionModel.Select)
            self.clearSelection()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if not self.itemAt(event.pos()):
            self.clearSelection()
            self.parent().clearAllSelectionsExcept(self)
        super().mousePressEvent(event)

    def connectScroll(self, otherWidgets):
        def syncScroll(value):
            for widget in otherWidgets:
                if widget.verticalScrollBar() is not self.verticalScrollBar():
                    widget.verticalScrollBar().setValue(value)
        self.verticalScrollBar().valueChanged.connect(syncScroll)


class CustomEvent(QEvent):
    def __init__(self, fn):
        super().__init__(QEvent.User)
        self.fn = fn

    def execute(self):
        self.fn()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    demo = FilePathsPlaceholder()
    demo.show()
    sys.exit(app.exec_())