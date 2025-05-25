import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [status, setStatus] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // 从API获取状态信息
    fetch('/api/status')
      .then(response => {
        if (!response.ok) {
          throw new Error('网络请求失败');
        }
        return response.json();
      })
      .then(data => {
        setStatus(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>策略空间 - 量化交易系统</h1>
      </header>
      
      <main className="App-main">
        <section className="status-section">
          <h2>系统状态</h2>
          {loading ? (
            <p>加载中...</p>
          ) : error ? (
            <p className="error">错误: {error}</p>
          ) : (
            <div className="status-container">
              <p>API服务器: <span className="status-running">运行中</span></p>
              {status.data && (
                <>
                  <p>数据服务: <span className={`status-${status.data.services.data_service}`}>
                    {status.data.services.data_service === 'running' ? '运行中' : '未运行'}
                  </span></p>
                  <p>模型服务: <span className={`status-${status.data.services.model_service}`}>
                    {status.data.services.model_service === 'running' ? '运行中' : '未运行'}
                  </span></p>
                </>
              )}
            </div>
          )}
        </section>
        
        <section className="features-section">
          <h2>主要功能</h2>
          <div className="feature-grid">
            <div className="feature-card">
              <h3>数据分析</h3>
              <p>查看历史数据和实时市场数据分析</p>
              <button disabled>进入</button>
            </div>
            <div className="feature-card">
              <h3>策略管理</h3>
              <p>创建、测试和部署交易策略</p>
              <button disabled>进入</button>
            </div>
            <div className="feature-card">
              <h3>回测系统</h3>
              <p>使用历史数据测试交易策略的表现</p>
              <button disabled>进入</button>
            </div>
            <div className="feature-card">
              <h3>交易监控</h3>
              <p>实时监控交易活动和账户状态</p>
              <button disabled>进入</button>
            </div>
          </div>
        </section>
      </main>
      
      <footer className="App-footer">
        <p>策略空间 &copy; {new Date().getFullYear()} - 量化交易系统</p>
      </footer>
    </div>
  );
}

export default App; 