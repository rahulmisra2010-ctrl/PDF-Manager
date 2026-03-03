import tkinter as tk
from tkinter import filedialog, messagebox

class PDFManager:
    def __init__(self, master):
        self.master = master
        master.title("PDF Manager")
        master.geometry('800x600')
        master.configure(bg='red')

        self.label = tk.Label(master, text="PDF Manager", font=('Arial', 24), bg='red', fg='white')
        self.label.pack(pady=20)

        self.frame = tk.Frame(master, bg='white')
        self.frame.pack(pady=20, padx=20, fill=tk.BOTH, expand=True)

        self.left_column = tk.Frame(self.frame, bg='white')
        self.left_column.pack(side=tk.LEFT, fill=tk.Y)

        self.right_column = tk.Frame(self.frame, bg='white')
        self.right_column.pack(side=tk.RIGHT, fill=tk.Y)

        self.upload_button = tk.Button(self.left_column, text="Upload PDF", command=self.upload_pdf)
        self.upload_button.pack(pady=10)

        self.ocr_button = tk.Button(self.left_column, text="Run OCR", command=self.run_ocr)
        self.ocr_button.pack(pady=10)

        self.result_area = tk.Text(self.right_column, wrap=tk.WORD, height=20, width=50)
        self.result_area.pack(pady=10)

    def upload_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[('PDF Files', '*.pdf')])
        if not file_path:
            return
        self.result_area.insert(tk.END, f'Uploaded PDF: {file_path}\n')

    def run_ocr(self):
        # Here you would implement the advanced OCR logic
        self.result_area.insert(tk.END, 'Running OCR...\n')

        # Simulate AI correction (this is a placeholder)
        self.result_area.insert(tk.END, 'Applying AI corrections...\n')

if __name__ == '__main__':
    root = tk.Tk()
    pdf_manager = PDFManager(root)
    root.mainloop()