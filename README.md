# Privacy-Preserving Public Transport Demand Forecasting using Federated Learning

## Overview
This project presents a federated learning-based system for predicting public transport demand while preserving data privacy. Multiple transport operators collaboratively train a global model without sharing raw data.

The system simulates real-world multi-operator environments with non-IID data distributions and provides actionable insights such as trend analysis, anomaly detection, and service pattern classification.

---

##  Features
- Federated Learning using FedAvg and FedProx
- Privacy-preserving decentralized training
- Non-IID client simulation using geographic clustering
- Dynamic client onboarding and removal
- Demand forecasting using SGDRegressor
- Insights engine (trend analysis, anomaly detection, service pattern classification)
- Role-based dashboards (Authority, FL Coordinator, Operator)

---

##  Tech Stack
- Python (Flask)
- Scikit-learn (SGDRegressor)
- Pandas, NumPy
- React.js (Frontend)
- Federated Learning (FedAvg, FedProx)
- Data Visualization Libraries

---

##  System Architecture
The system follows a federated learning architecture:

1. Each client trains a local model using private data  
2. Model parameters are sent to a central server  
3. The server aggregates updates using FedAvg or FedProx  
4. The global model is redistributed to all clients  

No raw data is shared during the process, ensuring privacy preservation.

---

##  Dataset
- Source: Chicago Transit Authority (CTA)
- Time Range: 2001 – 2025
- Data Type: Monthly ridership per route
- Total Records: ~34,000+

---

##  Results
- Mean Absolute Error (MAE): 4,732 rides/route/month  
- Error Rate: ~2.7%  
- Convergence: 3–4 federated rounds  
- Robust performance under non-IID data  

---

##  Author
- Aasiya M 
