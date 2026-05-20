# Code Architecture & Walkthrough

As a senior developer, when we review code, we don't necessarily read every single `</div>` tag. Instead, we look at the **logical blocks**. Below is a structured, block-by-block walkthrough of the files we just worked on to help you understand the architecture, design patterns, and logic.

---

## 1. `chatbot.html` (The Rule-Based Assistant)
This file is a reusable UI component that gets injected into our other pages via Jinja2's `{% include 'chatbot.html' %}`. 

### HTML Structure (Lines 1-35)
* **`#chatbot-container`**: The absolute wrapper that pins the chatbot to the bottom right of the screen.
* **`#chatbot-bubble`**: The circular floating action button (FAB). This is what the user clicks to open the chat window. It uses a Bootstrap Icon (`bi-chat-dots-fill`).
* **`#chatbot-window`**: The actual chat interface (initially hidden with `d-none`). It contains:
  * **`#chatbot-header`**: The top bar with the bot's name and the close button.
  * **`#chatbot-messages`**: The scrollable container where chat bubbles are dynamically appended.
  * **`#chatbot-input-container`**: The input field and send button.

### CSS Styling (Lines 36-200)
* **Animations**: We use `@keyframes slideIn` to make the chat window smoothly slide up from the bottom when opened. 
* **Typing Indicator**: The `.typing-dot` animation uses staggered `animation-delay` (e.g., `-0.32s`, `-0.16s`) to create a bouncing wave effect while the bot is "thinking".
* **Message Bubbles**: The CSS distinguishes between `.message.assistant` (white background, aligned left) and `.message.user` (purple background, aligned right) to create a conversational layout.

### JavaScript Logic (Lines 202-293)
* **Event Listeners**: We attach click events to the bubble (to open) and the close button (to hide).
* **`addMessage(text, sender)`**: A helper function that creates a new `div`, assigns the correct CSS class based on the sender, and auto-scrolls the container to the bottom.
* **`showTyping()`**: Temporarily injects the bouncing dots animation into the chat while we wait for the logic to execute.
* **`handleSend()`**: The core rule-based engine:
  1. Grabs the user's input and converts it to lowercase (`lowerText`).
  2. Uses `setTimeout` to wait 1 second (simulating network latency so it feels like a real bot).
  3. Evaluates a series of `if/else if` statements to check for keywords (`includes('resume')`, `includes('drive')`).
  4. Removes the typing indicator and injects the corresponding hardcoded response.

---

## 2. `student_dashboard.html` & `student_dashboard.css` (Responsive Navigation)
The goal here was to upgrade the UI from a horizontal scrolling bar on mobile to a sleek, modern slide-in sidebar (Off-Canvas pattern).

### The HTML Updates
* **Mobile Toggle (`#sidebarToggle`)**: A floating button injected at the top of the `<body>` that only appears on mobile screens.
* **Overlay (`#sidebarOverlay`)**: A dark, semi-transparent `<div>` that covers the main content when the sidebar is open, focusing the user's attention on the navigation.
* **JavaScript Toggle Logic (Lines 799-828)**: 
  * Listens for a click on the toggle button and adds the `mobile-active` class to the sidebar, and `show` class to the overlay.
  * Also listens for clicks on the overlay itself or any sidebar link to auto-close the menu (a crucial UX best practice for mobile).

### The CSS Updates
* **Media Query (`@media (max-width: 991px)`)**: This acts as the breakpoint. Any screen smaller than 991px (tablets and phones) triggers our mobile rules.
* **`transform: translateX(-100%)`**: By default on mobile, the sidebar is pushed 100% off the left side of the screen (hidden).
* **`transform: translateX(0)`**: When the JS adds the `.mobile-active` class, the sidebar slides back into view. We use `transition: transform 0.3s ease` to make it smooth.
* **`.mobile-nav-toggle`**: Styled as a fixed circular button at the bottom-right. We use `z-index: 1001` to ensure it always floats above the rest of the dashboard content.

---

## 3. `home.html` (The Landing Page)
This is the public-facing entry point of the application.

### The Head / Meta (Lines 1-15)
* **Bootstrap Icons**: We injected `<link rel="stylesheet" href="...bootstrap-icons.css">` here. Without this, the chatbot's `bi-chat-dots-fill` icon would fail to render, leaving a blank purple circle.
* **Font Loading**: Pulls in the "Plus Jakarta Sans" font for a modern, tech-focused typography style.

### The Sections (Lines 16-507)
* **Navbar**: Sticky top navigation with anchor links (`#features`, `#about`) that rely on Bootstrap's ScrollSpy (`data-bs-spy="scroll"`) to highlight the active section as the user scrolls.
* **Hero Section**: The first impression. Uses CSS gradients (`.text-gradient`) and a floating image animation (`.animate-float`) to create a "premium" feel.
* **Roles / Features / Leadership**: Grid layouts (`row`, `col-md-4`, etc.) using Bootstrap's flexbox grid system to ensure the content stacks vertically on mobile but sits side-by-side on desktop.

### The Footer (Line 508-511)
* **`{% include 'chatbot.html' %}`**: The crucial Jinja template tag we added right before the `</body>` tag. This injects the entire chatbot HTML/CSS/JS block into the landing page without having to duplicate the code.
