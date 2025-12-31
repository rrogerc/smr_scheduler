'use client';

import { useState, useEffect } from 'react';
import { Octokit } from 'octokit';
import { Calendar, FileSpreadsheet, LogOut, Play, Loader2, Key, Download, AlertCircle } from 'lucide-react';

// Configuration - Update these if the repo owner/name changes
const REPO_OWNER = 'rrogerc';
const REPO_NAME = 'smr_scheduler';
const WORKFLOW_ID = 'generate_schedule.yml'; // The filename of the workflow

interface ScheduleFile {
  name: string;
  path: string;
  download_url: string;
  sha: string;
}

export default function Home() {
  const [token, setToken] = useState<string>('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [files, setFiles] = useState<ScheduleFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  // Form state
  const [selectedMonth, setSelectedMonth] = useState<string>((new Date().getMonth() + 2).toString()); // Default to next month
  const [selectedYear, setSelectedYear] = useState<string>(new Date().getFullYear().toString());

  const [verifying, setVerifying] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = localStorage.getItem('smr_scheduler_token');
    if (storedToken) {
      setToken(storedToken);
      // Verify stored token silently
      verifyAndLogin(storedToken, true);
    }
  }, []);

  const verifyAndLogin = async (authToken: string, isAutoLogin: boolean) => {
    if (isAutoLogin) setLoadingFiles(true);
    else setVerifying(true);
    
    setLoginError(null);

    try {
      const octokit = new Octokit({ auth: authToken });
      // Try to fetch to verify token
      const response = await octokit.request('GET /repos/{owner}/{repo}/contents/{path}', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: 'schedules',
      });

      // If we get here, token is valid
      localStorage.setItem('smr_scheduler_token', authToken);
      setIsAuthenticated(true);
      
      if (Array.isArray(response.data)) {
         const scheduleFiles = response.data
          .filter((file: any) => file.name.endsWith('.xlsx'))
          .map((file: any) => ({
            name: file.name,
            path: file.path,
            download_url: file.download_url,
            sha: file.sha,
          }))
          .sort((a, b) => b.name.localeCompare(a.name));
        
        setFiles(scheduleFiles);
      }
    } catch (error: any) {
      console.error('Login verification failed:', error);
      if (isAutoLogin) {
        // If auto-login fails, clear storage and logout
        localStorage.removeItem('smr_scheduler_token');
        setIsAuthenticated(false);
      } else {
        // Show user friendly error
        setLoginError("Access Denied. Please check that you copied the token correctly and try again.");
      }
    } finally {
      setVerifying(false);
      setLoadingFiles(false);
    }
  };

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    verifyAndLogin(token, false);
  };

  const handleLogout = () => {
    localStorage.removeItem('smr_scheduler_token');
    setToken('');
    setIsAuthenticated(false);
    setFiles([]);
  };

  const fetchSchedules = async (authToken: string) => {
    setLoadingFiles(true);
    try {
      const octokit = new Octokit({ auth: authToken });
      // Fetch contents of the 'schedules' directory
      const response = await octokit.request('GET /repos/{owner}/{repo}/contents/{path}', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: 'schedules',
      });

      if (Array.isArray(response.data)) {
        // Filter for Excel files and map to our interface
        const scheduleFiles = response.data
          .filter((file: any) => file.name.endsWith('.xlsx'))
          .map((file: any) => ({
            name: file.name,
            path: file.path,
            download_url: file.download_url,
            sha: file.sha,
          }))
          .sort((a, b) => b.name.localeCompare(a.name)); // Sort desc (newest first usually)
        
        setFiles(scheduleFiles);
      }
    } catch (error) {
      console.error('Error fetching schedules:', error);
      setMessage({ type: 'error', text: 'Failed to fetch schedules. Check your token and repo permissions.' });
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setMessage(null);
    try {
      const octokit = new Octokit({ auth: token });
      await octokit.request('POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        workflow_id: WORKFLOW_ID,
        ref: 'main', // Branch to run on
        inputs: {
          month: selectedMonth,
          year: selectedYear,
        },
      });

      setMessage({ type: 'success', text: `Successfully triggered schedule generation for ${selectedMonth}/${selectedYear}. It may take a few minutes to appear.` });
    } catch (error: any) {
      console.error('Error triggering workflow:', error);
      setMessage({ type: 'error', text: `Failed to trigger generation: ${error.message || 'Unknown error'}` });
    } finally {
      setGenerating(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-4">
        <div className="w-full max-w-md space-y-8 rounded-xl bg-white p-10 shadow-lg">
          <div className="text-center">
            <h2 className="mt-6 text-3xl font-extrabold text-gray-900">SMR Scheduler</h2>
            <p className="mt-2 text-sm text-gray-600">Enter your GitHub Personal Access Token to continue</p>
          </div>
          <form className="mt-8 space-y-6" onSubmit={handleLogin}>
            <div>
              <label htmlFor="token" className="sr-only">GitHub Token</label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <Key className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  id="token"
                  name="token"
                  type="password"
                  required
                  className="block w-full rounded-md border-0 py-3 pl-10 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6"
                  placeholder="ghp_..."
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </div>
            </div>

            {loginError && (
              <div className="rounded-md bg-red-50 p-3">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <AlertCircle className="h-5 w-5 text-red-400" aria-hidden="true" />
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-red-800">{loginError}</h3>
                  </div>
                </div>
              </div>
            )}

            <div>
              <button
                type="submit"
                disabled={verifying}
                className="group relative flex w-full justify-center rounded-md bg-blue-600 px-3 py-3 text-sm font-semibold text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:bg-blue-400 disabled:cursor-not-allowed"
              >
                {verifying ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  'Access Dashboard'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 justify-between">
            <div className="flex items-center">
              <Calendar className="h-8 w-8 text-blue-600" />
              <span className="ml-3 text-xl font-bold text-gray-900">SMR Scheduler Dashboard</span>
            </div>
            <div className="flex items-center">
              <button
                onClick={handleLogout}
                className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
              >
                <LogOut className="mr-2 h-4 w-4 text-gray-500" />
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-7xl py-10 px-4 sm:px-6 lg:px-8">
        {message && (
          <div className={`mb-6 rounded-md p-4 ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
            <div className="flex">
              <div className="flex-shrink-0">
                {message.type === 'success' ? <div className="h-5 w-5 rounded-full bg-green-400" /> : <AlertCircle className="h-5 w-5" />}
              </div>
              <div className="ml-3">
                <p className="text-sm font-medium">{message.text}</p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
          {/* Generator Section */}
          <div className="md:col-span-1">
            <div className="overflow-hidden rounded-lg bg-white shadow">
              <div className="bg-blue-600 px-4 py-5 sm:px-6">
                <h3 className="text-lg font-medium leading-6 text-white">Generate Schedule</h3>
              </div>
              <div className="px-4 py-5 sm:p-6">
                <div className="space-y-4">
                  <div>
                    <label htmlFor="month" className="block text-sm font-medium leading-6 text-gray-900">Month</label>
                    <select
                      id="month"
                      value={selectedMonth}
                      onChange={(e) => setSelectedMonth(e.target.value)}
                      className="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 sm:text-sm sm:leading-6"
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                        <option key={m} value={m}>{new Date(0, m - 1).toLocaleString('default', { month: 'long' })}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="year" className="block text-sm font-medium leading-6 text-gray-900">Year</label>
                    <select
                      id="year"
                      value={selectedYear}
                      onChange={(e) => setSelectedYear(e.target.value)}
                      className="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 sm:text-sm sm:leading-6"
                    >
                      {[2024, 2025, 2026, 2027].map((y) => (
                        <option key={y} value={y}>{y}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={handleGenerate}
                    disabled={generating}
                    className="flex w-full justify-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500 disabled:bg-blue-300 disabled:cursor-not-allowed"
                  >
                    {generating ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Play className="mr-2 h-5 w-5" />
                        Run Generator
                      </>
                    )}
                  </button>
                  <p className="text-xs text-gray-500">
                    This triggers a GitHub Action. The schedule will appear in the list below after 1-2 minutes.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* List Section */}
          <div className="md:col-span-2">
            <div className="overflow-hidden rounded-lg bg-white shadow">
              <div className="flex items-center justify-between border-b border-gray-200 px-4 py-5 sm:px-6">
                <h3 className="text-lg font-medium leading-6 text-gray-900">Available Schedules</h3>
                <button
                  onClick={() => fetchSchedules(token)}
                  className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-500"
                >
                  <RefreshCw className={`h-5 w-5 ${loadingFiles ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <ul role="list" className="divide-y divide-gray-200">
                {loadingFiles && files.length === 0 ? (
                  <li className="px-4 py-10 text-center text-gray-500">Loading files...</li>
                ) : files.length === 0 ? (
                  <li className="px-4 py-10 text-center text-gray-500">No schedules found.</li>
                ) : (
                  files.map((file) => (
                    <li key={file.sha} className="flex items-center justify-between px-4 py-4 hover:bg-gray-50 sm:px-6">
                      <div className="flex min-w-0 flex-1 items-center">
                        <div className="flex-shrink-0">
                          <FileSpreadsheet className="h-8 w-8 text-green-600" />
                        </div>
                        <div className="min-w-0 flex-1 px-4 md:grid md:grid-cols-2 md:gap-4">
                          <div>
                            <p className="truncate text-sm font-medium text-blue-600">{file.name}</p>
                            <p className="mt-1 flex items-center text-xs text-gray-500">
                              <span className="truncate">schedules/{file.name}</span>
                            </p>
                          </div>
                        </div>
                      </div>
                      <div>
                        <a
                          href={file.download_url}
                          className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
                        >
                          <Download className="mr-2 h-4 w-4 text-gray-500" />
                          Download
                        </a>
                      </div>
                    </li>
                  ))
                )}
              </ul>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}