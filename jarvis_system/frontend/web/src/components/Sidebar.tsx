import React from 'react';
import { NavLink } from 'react-router-dom';
import { 
  BookOpen, 
  CheckSquare, 
  MessageSquare, 
  Cpu, 
  Brain, 
  LineChart, 
  ShieldAlert,
  Fingerprint,
  Wifi,
  Eye,
  Link,
  MapPin
} from 'lucide-react';
import styles from './Sidebar.module.css';

const navItems = [
  { path: '/study', icon: BookOpen, label: 'Study & Learning' },
  { path: '/productivity', icon: CheckSquare, label: 'Productivity' },
  { path: '/communication', icon: MessageSquare, label: 'Communication' },
  { path: '/agent', icon: Cpu, label: 'Autonomous Agent' },
  { path: '/cognitive', icon: Brain, label: 'Cognitive Engine' },
  { path: '/analytics', icon: LineChart, label: 'Predictive Analytics' },
  { path: '/security', icon: ShieldAlert, label: 'Security Core' },
  { path: '/twin', icon: Fingerprint, label: 'Digital Twin' },
  { path: '/neural', icon: Wifi, label: 'Neural Interface' },
  { path: '/arvr', icon: Eye, label: 'AR/VR Spatial' },
  { path: '/web3', icon: Link, label: 'Blockchain Agent' },
  { path: '/iot', icon: MapPin, label: 'IoT & India Ops' },
];

export const Sidebar: React.FC = () => {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <h1 className="text-gradient">JARVIS</h1>
        <span className={styles.version}>QUANTUM v2.0</span>
      </div>
      
      <nav className={styles.nav}>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink 
              key={item.path} 
              to={item.path} 
              className={({ isActive }) => 
                isActive ? `${styles.navItem} ${styles.active}` : styles.navItem
              }
            >
              <Icon className={styles.icon} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className={styles.footer}>
        <div className={styles.statusIndicator}>
          <div className={styles.dot}></div>
          <span>System Online</span>
        </div>
      </div>
    </aside>
  );
};
