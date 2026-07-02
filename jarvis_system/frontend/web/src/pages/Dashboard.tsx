import React from 'react';
import { Activity, ShieldCheck, Zap } from 'lucide-react';
import styles from './Dashboard.module.css';

export const Dashboard: React.FC = () => {
  return (
    <div className={styles.dashboard}>
      <header className={styles.header}>
        <div>
          <h2 className="text-gradient">System Overview</h2>
          <p className={styles.greeting}>Welcome back, Jay. All protocols nominal.</p>
        </div>
        <button className="btn-primary">Initialize Workflow</button>
      </header>

      <div className={styles.grid}>
        {/* Memory Palace Stat */}
        <div className={`glass-panel ${styles.card}`}>
          <div className={styles.cardHeader}>
            <Activity size={24} />
            <h3>Memory Palace</h3>
          </div>
          <div>
            <span className={styles.statValue}>1,402</span>
            <span className={styles.statLabel}> Active Nodes</span>
          </div>
          <p className={styles.statLabel}>Cognitive Engine is mapping new connections.</p>
        </div>

        {/* Security Core Stat */}
        <div className={`glass-panel ${styles.card}`}>
          <div className={styles.cardHeader}>
            <ShieldCheck size={24} color="#10b981" />
            <h3>Security Core</h3>
          </div>
          <div>
            <span className={styles.statValue}>Real</span>
            <span className={styles.statLabel}> Identity Layer</span>
          </div>
          <p className={styles.statLabel}>Zero-Knowledge encryption active. 0 jailbreak attempts.</p>
        </div>

        {/* Performance Stat */}
        <div className={`glass-panel ${styles.card}`}>
          <div className={styles.cardHeader}>
            <Zap size={24} color="#f59e0b" />
            <h3>System Performance</h3>
          </div>
          <div>
            <span className={styles.statValue}>42ms</span>
            <span className={styles.statLabel}> API Latency</span>
          </div>
          <p className={styles.statLabel}>Quantum container overhead is minimal.</p>
        </div>
      </div>
    </div>
  );
};
