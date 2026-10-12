import { createBrowserRouter, Navigate } from 'react-router'
import { LoginPage } from '@/features/auth/login-page'
import { SignupPage } from '@/features/auth/signup-page'
import { VerifyEmailPage } from '@/features/auth/verify-email-page'
import { GeneratePage } from '@/features/generate/generate-page'
import { InputPage } from '@/features/input/input-page'
import { PrivacyPage } from '@/features/privacy/privacy-page'
import { ProjectsPage } from '@/features/projects/projects-page'
import { ReviewPage } from '@/features/review/review-page'
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
          {
            path: 'projects/:projectId',
            element: <WorkspaceLayout />,
            children: [
              { index: true, element: <WorkspaceIndex /> },
              { path: 'input', element: <InputPage /> },
              { path: 'review', element: <ReviewPage /> },
              { path: 'generate', element: <GeneratePage /> },
              { path: 'diagrams/:diagramId', element: <ViewerPage /> },
            ],
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export const router = createBrowserRouter(routes)
