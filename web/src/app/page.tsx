'use client';

import { useState, useEffect } from 'react';
import { Octokit } from 'octokit';
import { Calendar, FileSpreadsheet, LogOut, Play, Loader2, Key, Download, AlertCircle, RefreshCw, Info, Users } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Configuration - Update these if the repo owner/name changes
const REPO_OWNER = 'rrogerc';
const REPO_NAME = 'smr_scheduler';
const WORKFLOW_ID = 'generate_term_schedule.yml'; // The filename of the workflow

interface ScheduleFile {
  name: string;
  path: string;
  download_url: string;
  sha: string;
  lastUpdated?: string; // Add timestamp field
}

interface RosterEntry {
  name: string;
  shifts?: number;
}

type Tab = 'schedules' | 'roster' | 'how-it-works';

export default function Home() {
  const [token, setToken] = useState<string>('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('schedules');
  const [files, setFiles] = useState<ScheduleFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
  const [readme, setReadme] = useState<string>('');
  const [loadingReadme, setLoadingReadme] = useState(false);

  // Form state
  const [selectedTerm, setSelectedTerm] = useState<string>('Fall');
  const [selectedYear, setSelectedYear] = useState<string>(new Date().getFullYear().toString());

  // Roster state
  const [rosterTerm, setRosterTerm] = useState<string>('Fall');
  const [rosterYear, setRosterYear] = useState<string>(new Date().getFullYear().toString());
  const [refreshingRoster, setRefreshingRoster] = useState(false);

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

  // Helper to fetch last commit date for a file
  const fetchLastCommitDate = async (octokit: Octokit, path: string): Promise<string | undefined> => {
    try {
      const commits = await octokit.request('GET /repos/{owner}/{repo}/commits', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: path,
        per_page: 1,
      });
      if (commits.data.length > 0) {
        return commits.data[0].commit.committer?.date;
      }
    } catch (error) {
      console.error(`Error fetching commit date for ${path}:`, error);
    }
    return undefined;
  };

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
         let scheduleFiles: ScheduleFile[] = response.data
          .filter((file: any) => file.name.endsWith('.xlsx'))
          .map((file: any) => ({
            name: file.name,
            path: file.path,
            download_url: file.download_url,
            sha: file.sha,
          }));
        
        // Fetch timestamps in parallel
        scheduleFiles = await Promise.all(scheduleFiles.map(async (file) => {
            const date = await fetchLastCommitDate(octokit, file.path);
            return { ...file, lastUpdated: date };
        }));

        // Sort by date (newest first), falling back to name
        scheduleFiles.sort((a, b) => {
            if (a.lastUpdated && b.lastUpdated) {
                return new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime();
            }
            return b.name.localeCompare(a.name);
        });
        
        setFiles(scheduleFiles);
      }

      // Also fetch README and Roster (default)
      fetchReadme(authToken);
      fetchRoster(authToken, 'Fall', new Date().getFullYear().toString());

    } catch (error: any) {
      console.error('Login verification failed:', error);
      if (isAutoLogin) {
        localStorage.removeItem('smr_scheduler_token');
        setIsAuthenticated(false);
      }
      else {
        setLoginError("Access Denied. Please check that you copied the token correctly and try again.");
      }
    } finally {
      setVerifying(false);
      setLoadingFiles(false);
    }
  };

  const fetchReadme = async (authToken: string) => {
    setLoadingReadme(true);
    try {
      const octokit = new Octokit({ auth: authToken });
      const response = await octokit.request('GET /repos/{owner}/{repo}/contents/{path}', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: 'README.md',
      });
      
      if ('content' in response.data) {
        const decoded = atob(response.data.content);
        setReadme(decoded);
      }
    } catch (error) {
      console.error('Error fetching README:', error);
    } finally {
      setLoadingReadme(false);
    }
  };

  const fetchRoster = async (authToken: string, term: string, year: string) => {
    setLoadingRoster(true);
    setRoster([]); // Clear old roster while loading
    try {
      const octokit = new Octokit({ auth: authToken });
      const response = await octokit.request('GET /repos/{owner}/{repo}/contents/{path}', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: `docs/rosters/roster_${term}_${year}.json`,
      });
      
      if ('content' in response.data) {
        const decoded = atob(response.data.content);
        const data = JSON.parse(decoded);
        if (Array.isArray(data)) {
          setRoster(data);
        }
      }
    } catch (error) {
      console.error('Error fetching Roster:', error);
      // It's okay if roster.json doesn't exist yet
    } finally {
      setLoadingRoster(false);
    }
  };

  const handleRefreshRoster = async () => {
    setRefreshingRoster(true);
    setMessage(null);
    try {
      const octokit = new Octokit({ auth: token });
      const response = await octokit.request('POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        workflow_id: 'refresh_roster.yml',
        ref: 'main',
        inputs: {
          term: rosterTerm,
          year: rosterYear,
        },
      });

      if (response.status === 204) {
        const msg = `Roster refresh triggered for ${rosterTerm} ${rosterYear}. It may take a minute.`;
        setMessage({ type: 'success', text: msg });
        alert(msg);
      } else {
        throw new Error(`Unexpected status: ${response.status}`);
      }
    } catch (error: any) {
      console.error('Error triggering roster refresh:', error);
      let errMsg = error.message || 'Unknown error';
      if (error.status === 403 || error.status === 404) {
        errMsg = "Failed to trigger. Please ensure your Token has the 'workflow' scope enabled.";
      }
      setMessage({ type: 'error', text: errMsg });
      alert(errMsg);
    } finally {
      setRefreshingRoster(false);
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
    setReadme('');
    setRoster([]);
  };

  const fetchSchedules = async (authToken: string) => {
    setLoadingFiles(true);
    try {
      const octokit = new Octokit({ auth: authToken });
      const response = await octokit.request('GET /repos/{owner}/{repo}/contents/{path}', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        path: 'schedules',
      });

      if (Array.isArray(response.data)) {
        let scheduleFiles: ScheduleFile[] = response.data
          .filter((file: any) => file.name.endsWith('.xlsx'))
          .map((file: any) => ({
            name: file.name,
            path: file.path,
            download_url: file.download_url,
            sha: file.sha,
          }));

         // Fetch timestamps in parallel
         scheduleFiles = await Promise.all(scheduleFiles.map(async (file) => {
            const date = await fetchLastCommitDate(octokit, file.path);
            return { ...file, lastUpdated: date };
        }));

        // Sort by date (newest first), falling back to name
        scheduleFiles.sort((a, b) => {
            if (a.lastUpdated && b.lastUpdated) {
                return new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime();
            }
            return b.name.localeCompare(a.name);
        });
        
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
      const response = await octokit.request('POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches', {
        owner: REPO_OWNER,
        repo: REPO_NAME,
        workflow_id: WORKFLOW_ID,
        ref: 'main',
        inputs: {
          term: selectedTerm,
          year: selectedYear,
        },
      });

      if (response.status === 204) {
        const msg = `Successfully triggered schedule generation for ${selectedTerm} ${selectedYear}. It may take 1-2 minutes to appear in the list.`;
        setMessage({ type: 'success', text: msg });
        alert(msg); // Immediate feedback
      } else {
        throw new Error(`Unexpected status: ${response.status}`);
      }
    } catch (error: any) {
      console.error('Error triggering workflow:', error);
      let errMsg = error.message || 'Unknown error';
      if (error.status === 403 || error.status === 404) {
        errMsg = "Failed to trigger. Please ensure your Token has the 'workflow' scope enabled.";
      }
      setMessage({ type: 'error', text: errMsg });
      alert(errMsg);
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
            <div className="flex items-center space-x-4">
              <nav className="flex space-x-1 rounded-lg bg-gray-100 p-1" aria-label="Tabs">
                <button
                  onClick={() => setActiveTab('schedules')}
                  className={`${activeTab === 'schedules' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'} rounded-md px-3 py-1.5 text-sm font-medium transition-all`}
                >
                  <FileSpreadsheet className="mr-1.5 inline-block h-4 w-4" />
                  Schedules
                </button>
                <button
                  onClick={() => setActiveTab('roster')}
                  className={`${activeTab === 'roster' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'} rounded-md px-3 py-1.5 text-sm font-medium transition-all`}
                >
                  <Users className="mr-1.5 inline-block h-4 w-4" />
                  Roster
                </button>
                <button
                  onClick={() => setActiveTab('how-it-works')}
                  className={`${activeTab === 'how-it-works' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'} rounded-md px-3 py-1.5 text-sm font-medium transition-all`}
                >
                  <Info className="mr-1.5 inline-block h-4 w-4" />
                  How it Works
                </button>
              </nav>
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
        {activeTab === 'schedules' ? (
          <>
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
                        <label htmlFor="term" className="block text-sm font-medium leading-6 text-gray-900">Term</label>
                        <select
                          id="term"
                          value={selectedTerm}
                          onChange={(e) => setSelectedTerm(e.target.value)}
                          className="mt-2 block w-full rounded-md border-0 py-1.5 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 sm:text-sm sm:leading-6"
                        >
                          <option value="Fall">Fall</option>
                          <option value="Winter">Winter</option>
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
                              <div className="hidden md:block">
                                <p className="text-xs text-gray-400">
                                  Last updated:
                                </p>
                                <p className="text-xs text-gray-600">
                                  {file.lastUpdated 
                                    ? new Date(file.lastUpdated).toLocaleString() 
                                    : 'Unknown'}
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
          </>
        ) : activeTab === 'roster' ? (
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <div className="border-b border-gray-200 px-4 py-5 sm:px-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <h3 className="text-lg font-medium leading-6 text-gray-900">Roster (Raw Availability)</h3>
                <div className="flex items-center space-x-2">
                  <select
                    value={rosterTerm}
                    onChange={(e) => {
                      setRosterTerm(e.target.value);
                      fetchRoster(token, e.target.value, rosterYear);
                    }}
                    className="block rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 sm:text-sm sm:leading-6"
                  >
                    <option value="Fall">Fall</option>
                    <option value="Winter">Winter</option>
                  </select>
                  <select
                    value={rosterYear}
                    onChange={(e) => {
                      setRosterYear(e.target.value);
                      fetchRoster(token, rosterTerm, e.target.value);
                    }}
                    className="block rounded-md border-0 py-1.5 pl-3 pr-8 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-blue-600 sm:text-sm sm:leading-6"
                  >
                    {[2024, 2025, 2026, 2027].map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                  <button
                    onClick={handleRefreshRoster}
                    disabled={refreshingRoster}
                    className="inline-flex items-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 disabled:opacity-50"
                  >
                    <RefreshCw className={`mr-2 h-4 w-4 text-gray-500 ${refreshingRoster ? 'animate-spin' : ''}`} />
                    Refresh
                  </button>
                </div>
              </div>
            </div>
            <div className="px-4 py-5 sm:p-6">
              {loadingRoster && roster.length === 0 ? (
                 <div className="flex justify-center py-10">
                   <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                 </div>
              ) : roster.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <p>No roster data found for {rosterTerm} {rosterYear}.</p>
                  <p className="text-sm mt-1">Click "Refresh" to pull the latest data from the spreadsheet.</p>
                </div>
              ) : (
                <div className="flow-root">
                  <div className="-mx-4 -my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
                    <div className="inline-block min-w-full py-2 align-middle sm:px-6 lg:px-8">
                      <table className="min-w-full divide-y divide-gray-300">
                        <thead>
                          <tr>
                            <th scope="col" className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-0">Name</th>
                            <th scope="col" className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                          {roster.map((person) => (
                            <tr key={person.name}>
                              <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-0">{person.name}</td>
                              <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                                <span className="inline-flex items-center rounded-md bg-green-50 px-2 py-1 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20">
                                  Submitted
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <div className="border-b border-gray-200 px-4 py-5 sm:px-6">
              <h3 className="text-lg font-medium leading-6 text-gray-900">How it Works</h3>
            </div>
            <div className="px-4 py-5 sm:p-6">
              {loadingReadme ? (
                <div className="flex justify-center py-10">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                </div>
              ) : (
                <div className="prose prose-blue max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {readme || "Loading instructions..."}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <style jsx global>{`
        .prose h1 { font-size: 2.25rem; font-weight: 800; margin-bottom: 2rem; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem; }
        .prose h2 { font-size: 1.5rem; font-weight: 700; margin-top: 2rem; margin-bottom: 1rem; color: #1e40af; }
        .prose h3 { font-size: 1.25rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.75rem; }
        .prose p { margin-bottom: 1rem; line-height: 1.75; color: #374151; }
        .prose ul { list-style-type: disc; padding-left: 1.5rem; margin-bottom: 1rem; }
        .prose li { margin-bottom: 0.5rem; }
        .prose strong { font-weight: 700; color: #111827; }
        .prose a { color: #2563eb; text-decoration: underline; }
      `}</style>
    </div>
  );
}
