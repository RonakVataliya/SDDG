import { createBrowserRouter, Navigate } from 'react-router'
import { LoginPage } from '@/features/auth/login-page'
import { SignupPage } from '@/features/auth/signup-page'
import { VerifyEmailPage } from '@/features/auth/verify-email-page'
import { AdminLayout } from '@/features/admin/admin-layout'
import { ErrorsPage } from '@/features/admin/errors-page'
import { UsagePage } from '@/features/admin/usage-page'
import { UsersPage } from '@/features/admin/users-page'
import { BacklogPage } from '@/features/backlog/backlog-page'
import { DesignPage } from '@/features/design/design-page'
import { GeneratePage } from '@/features/generate/generate-page'
import { AcceptInvitePage } from '@/features/invitations/accept-invite-page'
import { InputPage } from '@/features/input/input-page'
import { ActivityPage } from '@/features/activity/activity-page'
import { MembersPage } from '@/features/members/members-page'
import { PrivacyPage } from '@/features/privacy/privacy-page'
import { ProjectsPage } from '@/features/projects/projects-page'
import { CoveragePage } from '@/features/reporting/coverage-page'
import { ItemsPage } from '@/features/review/items-page'
import { ReviewPage } from '@/features/review/review-page'
import { SearchPage } from '@/features/search/search-page'
import { SettingsPage } from '@/features/settings/settings-page'
import { TestsPage } from '@/features/tests/tests-page'
import { ViewerPage } from '@/features/viewer/viewer-page'
import { AppLayout } from './app-layout'
import { NotFoundPage } from './not-found-page'
import { RequireAuth } from './require-auth'
import { WorkspaceIndex, WorkspaceLayout } from './workspace-layout'

export const routes = [
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  { path: '/verify-email', element: <VerifyEmailPage /> },
  { path: '/privacy', element: <PrivacyPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to="/projects" replace /> },
          { path: 'projects', element: <ProjectsPage /> },
          { path: 'invite', element: <AcceptInvitePage /> },
          {
            path: 'projects/:projectId',
            element: <WorkspaceLayout />,
            children: [
              { index: true, element: <WorkspaceIndex /> },
              { path: 'input', element: <InputPage /> },
              { path: 'review', element: <ReviewPage /> },
              { path: 'items', element: <ItemsPage /> },
              { path: 'generate', element: <GeneratePage /> },
              { path: 'search', element: <SearchPage /> },
              { path: 'coverage', element: <CoveragePage /> },
              { path: 'backlog', element: <BacklogPage /> },
              { path: 'members', element: <MembersPage /> },
              { path: 'activity', element: <ActivityPage /> },
              { path: 'settings', element: <SettingsPage /> },
              { path: 'tests', element: <TestsPage /> },
              { path: 'design', element: <DesignPage /> },
              { path: 'diagrams/:diagramId', element: <ViewerPage /> },
            ],
          },
          {
            path: 'admin',
            element: <AdminLayout />,
            children: [
              { index: true, element: <Navigate to="users" replace /> },
              { path: 'users', element: <UsersPage /> },
              { path: 'usage', element: <UsagePage /> },
              { path: 'errors', element: <ErrorsPage /> },
            ],
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export const router = createBrowserRouter(routes)
