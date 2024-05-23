import asyncio
import io
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from PIL import Image, ImageTk
import PIL
# import cairocffi
# cairocffi.install_as_pycairo()
import cairo
import tempfile

from .PrinterOperation import PrinterOperation
from NiimPrintX.nimmy.bluetooth import find_device

from devtools import debug


class PrintOption:
    def __init__(self, root, parent, config):
        self.root = root
        self.parent = parent
        self.config = config
        self.frame = ttk.Frame(parent)
        self.create_widgets()
        self.print_op = PrinterOperation(self.config)
        self.check_heartbeat()

    def check_heartbeat(self):
        asyncio.run_coroutine_threadsafe(self.schedule_heartbeat(), self.root.async_loop)

    async def schedule_heartbeat(self):
        while True:
            # debug(self.config.printer_connected, self.config.print_job)
            if self.print_op.printer and not self.config.print_job:
                # debug("connected")
                state, hb = await self.print_op.heartbeat()
                self.root.after(0, lambda: self.update_status(state, hb))
            elif not self.config.print_job:
                # debug("not connected")
                self.root.after(0, lambda: self.update_status(False))
            await asyncio.sleep(5)

    def update_status(self, connected=False, hb_data=None):
        # debug(hb_data)
        # debug(f"Heartbeat received: {connected}")
        self.config.printer_connected = connected
        if not connected and self.connect_button["state"] != tk.DISABLED:
            self.connect_button.config(text="Connect")
            self.connect_button.config(state=tk.NORMAL)
        self.root.after(0, lambda: self.root.status_bar.update_status(connected))

    def create_widgets(self):
        print_button = tk.Button(self.parent, text="Print", command=self.display_print)
        print_button.pack(side=tk.RIGHT, padx=10)
        save_image_button = tk.Button(self.parent, text="Save Image", command=self.save_image)
        save_image_button.pack(side=tk.RIGHT, padx=10)
        self.connect_button = tk.Button(self.parent, text="Connect", command=self.printer_connect)
        self.connect_button.pack(side=tk.RIGHT, padx=10)

    def printer_connect(self):
        self.connect_button.config(state=tk.DISABLED)
        if not self.config.printer_connected:
            future = asyncio.run_coroutine_threadsafe(
                self.print_op.printer_connect(self.config.device), self.root.async_loop
            )
            future.add_done_callback(lambda f: self._update_device_status(f))
        else:
            future = asyncio.run_coroutine_threadsafe(
                self.print_op.printer_disconnect(), self.root.async_loop
            )
            future.add_done_callback(lambda f: self._update_device_status(f))

    def _update_device_status(self, future):
        result = future.result()
        if self.config.printer_connected:
            self.connect_button.config(text="Disconnect")
            self.connect_button.config(state=tk.NORMAL)
        else:
            self.connect_button.config(text="Connect")
            self.connect_button.config(state=tk.NORMAL)
            result = False
        self.root.after(0, lambda: self.root.status_bar.update_status(result))

    def display_print(self):
        # Export to PNG and display it in a pop-up window
        tmp_file = tempfile.NamedTemporaryFile()
        self.export_to_png(tmp_file.name)  # Save to file
        self.display_image_in_popup(tmp_file.name)  # Display in pop-up window
        tmp_file.close()

    def save_image(self):
        options = {
            'defaultextension': '.png',
            'filetypes': [('PNG files', '*.png')],
            'initialfile': 'niimprintx.png',  # Specify an initial file name
            'title': 'Save as PNG'
        }
        # Open the save as dialog and get the selected file name
        file_path = filedialog.asksaveasfilename(**options)
        if file_path:
            self.export_to_png(file_path)
            self.display_image_in_popup(file_path)

    def export_to_png(self, output_filename):
        width = self.config.canvas.winfo_reqwidth()
        height = self.config.canvas.winfo_reqheight()

        x1, y1, x2, y2 = self.config.canvas.bbox(self.config.bounding_box)
        bbox_width = x2 - x1
        bbox_height = y2 - y1

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(1, 1, 1)  # White background
        ctx.paint()

        # Drawing images (if any)
        if self.config.image_items:
            for img_id, img_props in self.config.image_items.items():
                coords = self.config.canvas.coords(img_id)
                resized_image = ImageTk.getimage(img_props["image"])
                with io.BytesIO() as buffer:
                    resized_image.save(buffer, format="PNG")
                    buffer.seek(0)
                    img_surface = cairo.ImageSurface.create_from_png(buffer)
                ctx.set_source_surface(img_surface, coords[0], coords[1])
                ctx.paint()

        # Drawing text items
        if self.config.text_items:
            for text_id, text_props in self.config.text_items.items():
                coords = self.config.canvas.coords(text_id)
                resized_image = ImageTk.getimage(text_props["font_image"])
                with io.BytesIO() as buffer:
                    resized_image.save(buffer, format="PNG")
                    buffer.seek(0)
                    img_surface = cairo.ImageSurface.create_from_png(buffer)
                ctx.set_source_surface(img_surface, coords[0], coords[1])
                ctx.paint()

        # Create a cropped surface to save
        cropped_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(bbox_width), int(bbox_height))
        cropped_ctx = cairo.Context(cropped_surface)
        cropped_ctx.set_source_surface(surface, -x1, -y1)
        cropped_ctx.paint()
        cropped_surface.write_to_png(output_filename)

    def display_image_in_popup(self, filename):
        # Create a new Toplevel window
        popup = tk.Toplevel(self.root)
        popup.title("Preview Image")

        # Load the PNG image with PIL and convert to ImageTk
        img = Image.open(filename)
        img_tk = ImageTk.PhotoImage(img)

        # Create a Label to display the image
        image_label = tk.Label(popup, image=img_tk)
        image_label.image = img_tk  # Keep a reference to avoid garbage collection
        image_label.pack(padx=10, pady=10)

        option_frame = tk.Frame(popup)
        option_frame.pack(fill=tk.X, padx=20, pady=10)
        self.print_density = tk.IntVar()
        self.print_density.set(3)
        tk.Label(option_frame, text="Density").pack(side=tk.LEFT)
        density_slider = tk.Spinbox(option_frame,
                                    from_=1,
                                    to=self.config.label_sizes[self.config.device]['density'],
                                    textvariable=self.print_density,
                                    width=4
                                    )
        density_slider.pack(side=tk.LEFT, padx=(10, 0))

        tk.Label(option_frame, text="Copies").pack(side=tk.LEFT, padx=(40, 0))
        self.print_copy = tk.IntVar()
        self.print_copy.set(1)
        print_copy_dropdown = tk.Spinbox(option_frame, from_=1, to=100,
                                         textvariable=self.print_copy,
                                         width=4
                                         )
        print_copy_dropdown.pack(side=tk.LEFT, padx=(10, 0))

        button_frame = tk.Frame(popup)
        button_frame.pack(fill=tk.X, padx=20, pady=10)

        self.print_button = tk.Button(button_frame, text="Print",
                                      command=lambda image=img, density=self.print_density.get(),
                                                     quantity=self.print_copy.get(): self.print_label(image, density,
                                                                                                      quantity))
        self.print_button.pack(side=tk.LEFT, expand=True, pady=10)

        close_button = tk.Button(button_frame, text="Close", command=popup.destroy)
        close_button.pack(side=tk.LEFT, expand=True, pady=10)

    def print_label(self, image, density, quantity):
        self.print_button.config(state=tk.DISABLED)
        self.config.print_job = True
        image = image.rotate(-int(90),PIL.Image.NEAREST, expand=True)
        future = asyncio.run_coroutine_threadsafe(
            self.print_op.print(image, density, quantity), self.root.async_loop
        )
        future.add_done_callback(lambda f: self._print_handler(f))

    def _print_handler(self, future):
        result = future.result()
        if result:
            # debug("print", result)
            self.config.print_job = False
            self.root.after(0, lambda: self.root.status_bar.update_status(result))
        self.print_button.config(state=tk.NORMAL)
