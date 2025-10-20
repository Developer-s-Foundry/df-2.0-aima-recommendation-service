# 🧩 Setting up Prometheus and Windows Exporter on Windows (Without Docker)

## 🪟 Overview
Since Docker installation failed on the system, the setup was done **natively on Windows**, using **Prometheus** and **Windows Exporter** to collect and visualize system metrics such as CPU, memory, and disk usage.

---

## ⚙️ Step 1: Install Windows Exporter

1. Visited the official repository:  
   [https://github.com/prometheus-community/windows_exporter/releases](https://github.com/prometheus-community/windows_exporter/releases)

2. Downloaded the latest **`windows_exporter-<version>-amd64.msi`** installer.

3. Ran the installer and accepted all defaults.  
   This installed the exporter as a **Windows Service**.

4. Confirmed it was running by visiting:  
   👉 `http://localhost:9182/metrics`  
   This endpoint exposes system metrics in Prometheus format.

---

## ⚙️ Step 2: Download and Set Up Prometheus

1. Went to the official Prometheus download page:  
   [https://prometheus.io/download/](https://prometheus.io/download/)

2. Downloaded the file:  
   **`prometheus-<version>.windows-amd64.zip`**

3. Extracted the contents to:  
   👉 `C:\Prometheus`

4. Opened the `prometheus.yml` configuration file located inside the Prometheus folder.

---

## ⚙️ Step 3: Configure Prometheus to Scrape Windows Metrics

Edited the `prometheus.yml` file to include both Prometheus itself and Windows Exporter as scrape targets:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'windows'
    static_configs:
      - targets: ['localhost:9182']
```

Saved the file.

---

## ⚙️ Step 4: Start Prometheus

1. Opened **PowerShell** or **Command Prompt**.  
2. Navigated to the Prometheus directory:
   ```powershell
   cd C:\Prometheus
   ```
3. Started Prometheus:
   ```powershell
   prometheus.exe --config.file=prometheus.yml
   ```
4. Verified Prometheus was running by opening:
   👉 `http://localhost:9090`

---

## ⚙️ Step 5: Verify Targets

In the Prometheus web interface:
- Navigated to **Status → Targets**
- Confirmed both:
  - `prometheus` → **UP**
  - `windows` → **UP**

This verified that Prometheus successfully scraped metrics from both itself and the Windows Exporter.

---

## ⚙️ Step 6: Test PromQL Queries

Tested several example queries in the **Graph** tab:

| Purpose | PromQL Query |
|----------|---------------|
| CPU utilization (%) | `avg(rate(windows_cpu_time_total{mode!="idle"}[5m])) * 100` |
| Available memory (MB) | `windows_memory_available_bytes / 1024 / 1024` |
| Disk free space (GB) | `windows_logical_disk_free_bytes / 1024 / 1024 / 1024` |

Metrics appeared successfully, confirming data collection was working.

---

## 🎯 Final Result

Prometheus and Windows Exporter were successfully configured **without Docker**.  
Prometheus is scraping Windows system metrics every 15 seconds and serving them through its web interface for queries and visualization.

---



# ⚙️ Step 7: Download and Install Erlang & RabbitMQ

RabbitMQ is the message broker used by the AIMAS Recommendation Service to publish system recommendations to other microservices (e.g., Alerts, Notifications, Teams).
Because RabbitMQ depends on the **Erlang runtime**, both must be installed and configured before running the service.

---

##  1️⃣ Install Erlang

### 🔗 Download

Visit the official Erlang downloads page:
👉 [https://www.erlang.org/downloads](https://www.erlang.org/downloads)

### 🧩 Steps

1. Scroll to the **Windows** section and download the latest **Erlang/OTP** installer.
   Example:

   ```
   otp_win64_27.0.exe
   ```
2. Run the installer and accept all defaults.
3. Once installed, locate the install folder, typically:

   ```
   C:\Program Files\Erlang OTP\
   ```
4. Add Erlang’s `bin` folder to your **PATH** environment variable:

   ```
   C:\Program Files\Erlang OTP\bin
   ```

### ✅ Verify installation

Open a new **Command Prompt** and type:

```bash
erl
```

You should see:

```
Erlang/OTP 27 [erts-14.0] [source] [64-bit] ...
Eshell V14.0
1>
```

To exit:

```erlang
q().
```

---

## 🧱 2️⃣ Install RabbitMQ

### 🔗 Download

Visit the official RabbitMQ download page:
👉 [https://www.rabbitmq.com/install-windows.html](https://www.rabbitmq.com/install-windows.html)

Or go directly to the GitHub releases:
👉 [https://github.com/rabbitmq/rabbitmq-server/releases](https://github.com/rabbitmq/rabbitmq-server/releases)

Download the latest Windows installer, e.g.:

```
rabbitmq-server-3.13.0.exe
```

### 🧩 Steps

1. Run the RabbitMQ installer and accept the default options.
2. Once installation completes, RabbitMQ will be installed as a **Windows Service**.
3. Locate RabbitMQ’s install folder (used later for PATH):

   ```
   C:\Program Files\RabbitMQ Server\rabbitmq_server-3.13.0\
   ```
4. Add RabbitMQ’s `sbin` folder to your **PATH**:

   ```
   C:\Program Files\RabbitMQ Server\rabbitmq_server-3.13.0\sbin
   ```

---

## 🧠 3️⃣ Enable RabbitMQ Management Plugin

To enable the Web UI (port 15672), open **Command Prompt as Administrator** and run:

```bash
rabbitmq-plugins enable rabbitmq_management
```

Restart the service:

```bash
net stop RabbitMQ
net start RabbitMQ
```

---

## 🧭 4️⃣ Verify Installation

### ✅ Start the RabbitMQ Service

```bash
net start RabbitMQ
```

### 🧩 Check RabbitMQ Status

```bash
rabbitmqctl status
```

If successful, you’ll see:

```
Status of node rabbit@YOURNAME ...
[{pid,1234},
 {running_applications,[{rabbit,"RabbitMQ","3.13.0"}, ...]}]
```

### 🧠 Check Open Ports

RabbitMQ uses the following default ports:

| Port         | Purpose                        |
| ------------ | ------------------------------ |
| 5672         | AMQP (used by your Python app) |
| 15672        | Management UI                  |
| 4369 / 25672 | Internal communication         |

---

## 🌐 5️⃣ Access the RabbitMQ Management UI

Open your browser and go to:
👉 [http://localhost:15672](http://localhost:15672)

**Default credentials:**

```
Username: guest
Password: guest
```

You should now see the **RabbitMQ Dashboard** 🎉

---

## 🧩 8️⃣ Start Everything Together

Once Erlang and RabbitMQ are verified:

1. Start RabbitMQ:

   ```bash
   net start RabbitMQ
   ```
2. Start Prometheus.
3. Start Windows Exporter.
4. Run your Recommendation Service:

   ```bash
   python scheduler.py
   ```
5. Watch recommendations appear in RabbitMQ under the **“recommendations”** exchange.

---

## ✅ Sanity Check Summary

| Component         | Verify Command                | Expected Result                   |
| ----------------- | ----------------------------- | --------------------------------- |
| Erlang            | `erl`                         | Opens Erlang shell                |
| RabbitMQ Service  | `rabbitmqctl status`          | Shows node info                   |
| Management UI     | `http://localhost:15672`      | Dashboard visible                 |
| Python Publisher  | `python scheduler.py`         | Publishes messages every interval |
| RabbitMQ Exchange | Dashboard → “recommendations” | JSON messages visible             |

---


# How to authenticate with auth gateway service to be sure it's a User..
# with proper access role that is accessing our endpoints
